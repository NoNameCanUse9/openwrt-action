#!/usr/bin/env python3
"""ImmortalWrt ImageBuilder - Build firmware via Docker."""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

WORK_DIR = Path("/tmp/imagebuilder")
FORMAT_CONFIGS = {
    "default": ["CONFIG_TARGET_IMAGES_GZIP=y"],
    "ext4": [
        "CONFIG_TARGET_IMAGES_GZIP=y",
        "CONFIG_TARGET_ROOTFS_PARTSIZE=104",
    ],
    "squashfs": [
        "CONFIG_TARGET_IMAGES_GZIP=y",
    ],
    "efi-ext4": [
        "CONFIG_TARGET_IMAGES_GZIP=y",
        "CONFIG_EFI_IMAGES=y",
        "CONFIG_TARGET_ROOTFS_PARTSIZE=104",
    ],
    "efi-squashfs": [
        "CONFIG_TARGET_IMAGES_GZIP=y",
        "CONFIG_EFI_IMAGES=y",
    ],
    "qcow2": [
        "CONFIG_TARGET_IMAGES_GZIP=y",
        "CONFIG_QCOW2_IMAGES=y",
    ],
    "vmdk": [
        "CONFIG_TARGET_IMAGES_GZIP=y",
        "CONFIG_VMDK_IMAGES=y",
    ],
    "vdi": [
        "CONFIG_TARGET_IMAGES_GZIP=y",
        "CONFIG_VDI_IMAGES=y",
    ],
}


def parse_args():
    p = argparse.ArgumentParser(description="Build ImmortalWrt firmware")
    p.add_argument("--target", required=True, help="Target, e.g. x86/64")
    p.add_argument("--version", required=True, help="Version, e.g. 24.10")
    p.add_argument("--format", default="default", choices=FORMAT_CONFIGS.keys())
    p.add_argument("--packages", default="", help="Extra packages (space-separated)")
    p.add_argument("--diy-script", default="scripts/diy.sh", help="Customization script")
    p.add_argument("--config", default=".config", help="Base config file")
    p.add_argument("--files", default="files", help="Custom files directory")
    p.add_argument("--output", default="output", help="Output directory")
    return p.parse_args()


def prepare_work_dir():
    if WORK_DIR.exists():
        shutil.rmtree(WORK_DIR)
    WORK_DIR.mkdir(parents=True)


def load_packages(config_path: Path) -> list[str]:
    """Extract packages from .config CONFIG_PACKAGE_xxx=y lines."""
    packages = []
    if not config_path.exists():
        return packages
    for line in config_path.read_text().splitlines():
        line = line.strip()
        if line.startswith("CONFIG_PACKAGE_") and line.endswith("=y"):
            pkg = line.removeprefix("CONFIG_PACKAGE_").removesuffix("=y")
            if pkg and not pkg.startswith("NOT_A_PACKAGE"):
                packages.append(pkg)
    return packages


def load_config_options(config_path: Path) -> list[str]:
    """Extract non-package config options from .config."""
    options = []
    if not config_path.exists():
        return options
    for line in config_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key = line.split("=", 1)[0]
            if not key.startswith("CONFIG_PACKAGE_"):
                options.append(line)
    return options


def build_package_list(base_packages: list[str], extra: str) -> str:
    """Merge base packages from .config with extra packages from workflow input."""
    merged = list(base_packages)
    for pkg in extra.split():
        pkg = pkg.strip()
        if pkg and pkg not in merged:
            merged.append(pkg)
    # Always ensure luci is present
    if "luci" not in merged:
        merged.append("luci")
    return " ".join(merged)


def build_config_file(base_options: list[str], format_name: str) -> Path:
    """Generate final .config fragment for imagebuilder."""
    lines = list(base_options)
    lines.extend(FORMAT_CONFIGS.get(format_name, FORMAT_CONFIGS["default"]))

    config_path = WORK_DIR / ".config"
    config_path.write_text("\n".join(lines) + "\n")
    return config_path


def run_diy_script(script_path: str):
    """Execute user customization script (P3TERX diy.sh pattern)."""
    script = Path(script_path).resolve()
    if not script.exists():
        print(f"[INFO] No diy script found at {script_path}, skipping.")
        return
    print(f"[INFO] Running customization script: {script}")
    repo_root = Path(__file__).resolve().parent.parent
    subprocess.run(["bash", str(script)], check=True, cwd=str(repo_root))


def prepare_files(src_dir: str) -> Path:
    """Copy user files into the work directory."""
    src = Path(src_dir)
    dst = WORK_DIR / "files"
    if src.exists() and any(src.iterdir()):
        shutil.copytree(src, dst)
        print(f"[INFO] Copied custom files from {src_dir}")
    else:
        dst.mkdir(exist_ok=True)
        print(f"[INFO] No custom files found in {src_dir}")
    return dst


def run_imagebuilder(target: str, version: str, packages: str, files_dir: Path):
    """Run immortalwrt/imagebuilder Docker container."""
    target_slug = target.replace("/", "_")
    image_tag = f"immortalwrt/imagebuilder:{version}-{target_slug}"

    print(f"\n{'=' * 50}")
    print(f"  Target:   {target}")
    print(f"  Version:  {version}")
    print(f"  Image:    {image_tag}")
    print(f"  Packages: {packages}")
    print(f"{'=' * 50}\n")

    output_dir = WORK_DIR / "output"
    output_dir.mkdir(exist_ok=True)

    docker_cmd = [
        "docker", "run", "--rm", "--pull", "always",
        "-v", f"{files_dir}:/builder/files:ro",
        "-v", f"{output_dir}:/builder/bin/targets",
        "-e", f"PROFILE={target}",
        "-e", f"PACKAGES={packages}",
        "-e", "FILES=/builder/files",
        image_tag,
        "bash", "-c", "set -e && make image",
    ]

    print(f"[CMD] {' '.join(docker_cmd)}\n")
    result = subprocess.run(docker_cmd)

    if result.returncode != 0:
        print(f"\n[ERROR] Docker build failed with exit code {result.returncode}")
        sys.exit(1)

    return output_dir


def collect_output(output_dir: Path, dest: str):
    """Copy built firmware to the final output directory."""
    dest_path = Path(dest)
    if dest_path.exists():
        shutil.rmtree(dest_path)

    if output_dir.exists() and any(output_dir.iterdir()):
        shutil.copytree(output_dir, dest_path)
        print(f"\n[INFO] Firmware copied to {dest_path}/")
        for f in sorted(dest_path.rglob("*")):
            if f.is_file():
                size_mb = f.stat().st_size / (1024 * 1024)
                print(f"  {f.relative_to(dest_path)}  ({size_mb:.1f} MB)")
    else:
        print("[WARN] No output files found!")
        sys.exit(1)


def main():
    args = parse_args()
    repo_root = Path(__file__).resolve().parent.parent
    os.chdir(repo_root)

    print(f"[INFO] Repo root: {repo_root}")

    # 1. Prepare workspace
    prepare_work_dir()

    # 2. Load base config and packages
    config_path = Path(args.config)
    base_packages = load_packages(config_path)
    base_options = load_config_options(config_path)
    print(f"[INFO] Base packages from .config: {base_packages}")

    # 3. Run customization script
    run_diy_script(args.diy_script)

    # 4. Merge packages
    packages = build_package_list(base_packages, args.packages)

    # 5. Generate format config
    config_file = build_config_file(base_options, args.format)
    print(f"[INFO] Format config ({args.format}):")
    print(config_file.read_text())

    # 6. Prepare custom files
    files_dir = prepare_files(args.files)

    # 7. Build
    output_dir = run_imagebuilder(args.target, args.version, packages, files_dir)

    # 8. Collect output
    collect_output(output_dir, args.output)

    print("\n[DONE] Build completed successfully!")


if __name__ == "__main__":
    main()
