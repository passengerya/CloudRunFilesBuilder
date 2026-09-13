#!/bin/bash
set -e

# 从 dl.openwrt.ai (kiddin9) 下载 lucky 各平台 ipk
# lucky 主程序按架构区分, luci-app-lucky 为 all 架构

declare -A PLATFORMS=(
  ["x86"]="x86_64"
  ["arm64"]="aarch64_generic"
  ["a53"]="aarch64_cortex-a53"
)

OUT_DIR=$(pwd)
mkdir -p x86 arm64 a53

for dir in "${!PLATFORMS[@]}"; do
  arch="${PLATFORMS[$dir]}"
  BASE_URL="https://dl.openwrt.ai/packages-24.10/${arch}/kiddin9/"
  echo "[+] 获取 ${dir} (${arch}) 目录列表..."

  page=$(curl -sL --max-time 60 "$BASE_URL")

  # lucky 主程序 ipk(架构相关)
  LUCKY_IPK=$(echo "$page" | grep -oP 'href="\K[^"]*lucky_[^"]+\.ipk' | head -n1)
  # luci-app-lucky ipk(all 架构, 各目录相同)
  LUCI_IPK=$(echo "$page" | grep -oP 'href="\K[^"]*luci-app-lucky_[^"]+\.ipk' | head -n1)

  if [ -n "$LUCKY_IPK" ]; then
    echo "[+] 下载 $LUCKY_IPK"
    curl -sL --max-time 300 -o "${dir}/${LUCKY_IPK}" "${BASE_URL}${LUCKY_IPK}"
  else
    echo "[!] 未找到 ${arch} 的 lucky ipk"
  fi

  if [ -n "$LUCI_IPK" ]; then
    echo "[+] 下载 $LUCI_IPK"
    curl -sL --max-time 300 -o "${dir}/${LUCI_IPK}" "${BASE_URL}${LUCI_IPK}"
  else
    echo "[!] 未找到 luci-app-lucky ipk"
  fi
done

# 提取版本号(取 x86 的 lucky ipk 文件名, 如 lucky_2.20.2-r13_x86_64.ipk -> 2.20.2-r13)
LUCKY_FILE=$(ls x86/lucky_*.ipk 2>/dev/null | head -n1)
if [ -n "$LUCKY_FILE" ]; then
  VERSION=$(basename "$LUCKY_FILE" | sed -n 's/^lucky_\([0-9][^_]*\)_.*\.ipk$/\1/p')
  echo "VERSION=$VERSION" >> $GITHUB_ENV
  echo "✅ 提取到版本号: $VERSION"
else
  echo "⚠️ 未找到 x86 的 lucky ipk, 使用日期兜底"
  echo "VERSION=$(date +'%Y.%m.%d')" >> $GITHUB_ENV
fi

echo "✅ lucky 下载完成"
ls -lh */*.ipk 2>/dev/null | cat
