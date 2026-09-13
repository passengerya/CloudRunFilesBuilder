#!/bin/bash
set -euo pipefail

echo "=== Parsing release assets ==="

if [ ! -f release.json ]; then
  echo "❌ release.json not found!"
  exit 1
fi

# 解析 URL
X86_DAED_URL=$(jq -r '.assets[] | select(.name | test("daed-.*-x86_64\\.apk$")) | .browser_download_url' release.json | head -n1)
X86_DAE_URL=$(jq -r '.assets[] | select(.name | test("dae-.*-x86_64\\.apk$")) | .browser_download_url' release.json | head -n1)

ARM_A53_DAED_URL=$(jq -r '.assets[] | select(.name | test("daed-.*-aarch64_cortex-a53\\.apk$")) | .browser_download_url' release.json | head -n1)
ARM_A53_DAE_URL=$(jq -r '.assets[] | select(.name | test("dae-.*-aarch64_cortex-a53\\.apk$")) | .browser_download_url' release.json | head -n1)

ARM_GENERIC_DAED_URL=$(jq -r '.assets[] | select(.name | test("daed-.*-aarch64_generic\\.apk$")) | .browser_download_url' release.json | head -n1)
ARM_GENERIC_DAE_URL=$(jq -r '.assets[] | select(.name | test("dae-.*-aarch64_generic\\.apk$")) | .browser_download_url' release.json | head -n1)

echo "cat release.json======"
cat release.json
# LUCI 主程序 apk：优先从 release.json 动态解析最新版，解析失败时用固定版本兜底
LUCI_MAIN_URL=$(jq -r '.assets[] | select(.name | test("luci-app-daede-.*-x86_64\\.apk$")) | .browser_download_url' release.json | head -n1)
[ -n "$LUCI_MAIN_URL" ] || LUCI_MAIN_URL="https://github.com/kenzok8/openwrt-daede/releases/download/v2026.09.07-r2/luci-app-daede-1.15-r2-x86_64.apk"


# vmlinux-btf apk：优先从 release.json 动态解析最新版，解析失败时用固定版本兜底
X86_VMLINUX_BTF_URL=$(jq -r '.assets[] | select(.name | test("vmlinux-btf-.*-x86_64\\.apk$")) | .browser_download_url' release.json | head -n1)
ARM_A53_VMLINUX_BTF_URL=$(jq -r '.assets[] | select(.name | test("vmlinux-btf-.*-aarch64_cortex-a53\\.apk$")) | .browser_download_url' release.json | head -n1)
ARM_GENERIC_VMLINUX_BTF_URL=$(jq -r '.assets[] | select(.name | test("vmlinux-btf-.*-aarch64_generic\\.apk$")) | .browser_download_url' release.json | head -n1)

[ -n "$X86_VMLINUX_BTF_URL" ] || X86_VMLINUX_BTF_URL="https://github.com/kenzok8/openwrt-daede/releases/download/v2026.09.07-r2/vmlinux-btf-6.12.103-r1-x86_64.apk"
[ -n "$ARM_A53_VMLINUX_BTF_URL" ] || ARM_A53_VMLINUX_BTF_URL="https://github.com/kenzok8/openwrt-daede/releases/download/v2026.09.07-r2/vmlinux-btf-6.12.103-r1-aarch64_cortex-a53.apk"
[ -n "$ARM_GENERIC_VMLINUX_BTF_URL" ] || ARM_GENERIC_VMLINUX_BTF_URL="https://github.com/kenzok8/openwrt-daede/releases/download/v2026.09.07-r2/vmlinux-btf-6.12.103-r1-aarch64_generic.apk"

# 正确写入 GITHUB_ENV（关键修复）
{
  echo "X86_DAED_URL=$X86_DAED_URL"
  echo "X86_DAE_URL=$X86_DAE_URL"
  echo "X86_VMLINUX_BTF_URL=$X86_VMLINUX_BTF_URL"
  echo "ARM_A53_DAED_URL=$ARM_A53_DAED_URL"
  echo "ARM_A53_DAE_URL=$ARM_A53_DAE_URL"
  echo "ARM_A53_VMLINUX_BTF_URL=$ARM_A53_VMLINUX_BTF_URL"
  echo "ARM_GENERIC_DAED_URL=$ARM_GENERIC_DAED_URL"
  echo "ARM_GENERIC_DAE_URL=$ARM_GENERIC_DAE_URL"
  echo "ARM_GENERIC_VMLINUX_BTF_URL=$ARM_GENERIC_VMLINUX_BTF_URL"
  echo "LUCI_MAIN_URL=$LUCI_MAIN_URL"
} >> $GITHUB_ENV

# 调试输出
echo "✅ Parse completed successfully!"
echo "LUCI_MAIN_URL     = ${LUCI_MAIN_URL:-EMPTY}"
echo "X86_DAED_URL      = ${X86_DAED_URL:-EMPTY}"
echo "ARM_GENERIC_DAED_URL = ${ARM_GENERIC_DAED_URL:-EMPTY}"

if [ -z "$LUCI_MAIN_URL" ] || [ -z "$X86_DAED_URL" ]; then
  echo "⚠️ Some URLs are empty!"
else
  echo "✅ All main URLs parsed successfully."
fi
