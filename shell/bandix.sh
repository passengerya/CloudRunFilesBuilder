#!/bin/bash
set -e

# 下载 bandix 各平台 ipk(全部来自 timsaya 官方 Release, 版本配套):
# - bandix 主程序:          timsaya/openwrt-bandix 最新 Release(各架构 ipk)
# - luci-app-bandix:        timsaya/luci-app-bandix 最新 Release(_all ipk)
# - luci-i18n-bandix-zh-cn: 同 luci-app-bandix Release(_all ipk, Depends: luci-app-bandix)
#
# 2026-09-23 变更: 从 kiddin9(dl.openwrt.ai)切换到 timsaya 官方 Release。
# kiddin9 的 luci-app-bandix 内置 zh-cn lmo, 与独立语言包产生
# opkg check_data_file_clashes 导致下游固件构建失败, 且版本落后(0.11.1);
# timsaya 主包不含 lmo、语言包独立发布, 三者配套安装无冲突。

declare -A PLATFORMS=(
  ["x86"]="x86_64"
  ["arm64"]="aarch64_generic"
  ["a53"]="aarch64_cortex-a53"
)

API_HDR=(-H "Accept: application/vnd.github+json")
if [ -n "$GITHUB_TOKEN" ]; then
  API_HDR+=(-H "Authorization: Bearer $GITHUB_TOKEN")
fi

mkdir -p x86 arm64 a53

BIN_REL=$(curl -s --max-time 60 "${API_HDR[@]}" https://api.github.com/repos/timsaya/openwrt-bandix/releases/latest)
LUCI_REL=$(curl -s --max-time 60 "${API_HDR[@]}" https://api.github.com/repos/timsaya/luci-app-bandix/releases/latest)

for dir in "${!PLATFORMS[@]}"; do
  arch="${PLATFORMS[$dir]}"
  echo "[+] 获取 ${dir} (${arch}) 资产..."

  BIN_URL=$(echo "$BIN_REL" | jq -r --arg re "^bandix_.*_${arch}\\.ipk$" \
    '.assets[] | select(.name | test($re)) | .browser_download_url' | head -n1)
  LUCI_URL=$(echo "$LUCI_REL" | jq -r \
    '.assets[] | select(.name | test("^luci-app-bandix_.*_all\\.ipk$")) | .browser_download_url' | head -n1)
  I18N_URL=$(echo "$LUCI_REL" | jq -r \
    '.assets[] | select(.name | test("^luci-i18n-bandix-zh-cn_.*_all\\.ipk$")) | .browser_download_url' | head -n1)

  for url in "$BIN_URL" "$LUCI_URL" "$I18N_URL"; do
    if [ -z "$url" ] || [ "$url" = "null" ]; then
      echo "[!] 未找到该平台的资产之一, 跳过"
      continue
    fi
    fname=$(basename "$url")
    echo "[+] 下载 $fname"
    curl -sL --retry 3 --retry-delay 3 --max-time 300 "${API_HDR[@]}" -o "${dir}/${fname}" "$url"
  done
done

# 提取版本号(取 x86 的 bandix ipk 文件名, 如 bandix_0.12.10-r1_x86_64.ipk -> 0.12.10-r1)
BANDIX_FILE=$(ls x86/bandix_*.ipk 2>/dev/null | head -n1)
if [ -n "$BANDIX_FILE" ]; then
  VERSION=$(basename "$BANDIX_FILE" | sed -n 's/^bandix_\([0-9][^_]*\)_.*\.ipk$/\1/p')
  echo "VERSION=$VERSION" >> $GITHUB_ENV
  echo "✅ 提取到版本号: $VERSION"
else
  echo "⚠️ 未找到 x86 的 bandix ipk, 使用日期兜底"
  echo "VERSION=$(date +'%Y.%m.%d')" >> $GITHUB_ENV
fi

echo "✅ bandix 下载完成"
ls -lh */*.ipk 2>/dev/null | cat
