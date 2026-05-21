#!/bin/bash
#============================================================
# Description: DIY script for ImmortalWrt ImageBuilder
#
# This script runs BEFORE the image build.
# You can use it to modify packages, config, or files.
#
# Examples:
#   - Add/remove packages in .config
#   - Modify files/ directory content
#   - Download additional ipk packages
#============================================================

# --- Example: Add extra packages to .config ---
# sed -i '/^CONFIG_PACKAGE_luci=y/a CONFIG_PACKAGE_luci-app-ssr-plus=y' .config

# --- Example: Download an ipk and place it in files ---
# wget -P files/root/ https://example.com/some-package.ipk

# --- Example: Generate a config file inside files/ ---
# mkdir -p files/etc/config
# cat > files/etc/config/network <<'EOF'
# config interface 'lan'
#     option type 'bridge'
#     option ifname 'eth0'
#     option proto 'static'
#     option ipaddr '192.168.1.1'
#     option netmask '255.255.255.0'
# EOF

echo "DIY script completed."
