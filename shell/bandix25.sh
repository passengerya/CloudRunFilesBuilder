#!/bin/bash
set -e

# 下载 bandix 各平台 apk(全部来自 timsaya 官方 Release, 版本配套):
# - bandix 主程序:          timsaya/openwrt-bandix 最新 Release(各架构 apk)
# - luci-app-bandix:        timsaya/luci-app-bandix 最新 Release(_all apk)
# - luci-i18n-bandix-zh-cn: 同 luci-app-bandix Release(_all apk)
#
# 2026-09-24 新增: 25.12 通道此前缺 bandix(dl.openwrt.ai 无 25.12 包);
# timsaya 官方 Release 双格式齐备后补齐本通道。apk 文件名带架构后缀,
# 由 normalize_apk_names.py 统一规范为 name-version.apk(imagebuilder 索引要求)。

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

  BIN_URL=$(echo "$BIN_REL" | jq -r --arg re "^bandix-.*_${arch}\\.apk$" \
    '.assets[] | select(.name | test($re)) | .browser_download_url' | head -n1)
  LUCI_URL=$(echo "$LUCI_REL" | jq -r \
    '.assets[] | select(.name | test("^luci-app-bandix-.*\\.apk$")) | .browser_download_url' | head -n1)
  I18N_URL=$(echo "$LUCI_REL" | jq -r \
    '.assets[] | select(.name | test("^luci-i18n-bandix-zh-cn-.*\\.apk$")) | .browser_download_url' | head -n1)

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

# 提取版本号(取 x86 的 bandix apk 文件名, 如 bandix-0.12.10-r1_x86_64.apk -> 0.12.10-r1)
BANDIX_FILE=$(ls x86/bandix-*.apk 2>/dev/null | head -n1)
if [ -n "$BANDIX_FILE" ]; then
  VERSION=$(basename "$BANDIX_FILE" | sed -n 's/^bandix-\([0-9][^-]*\)_.*\.apk$/\1/p')
  echo "VERSION=$VERSION" >> $GITHUB_ENV
  echo "✅ 提取到版本号: $VERSION"
else
  echo "⚠️ 未找到 x86 的 bandix apk, 使用日期兜底"
  echo "VERSION=$(date +'%Y.%m.%d')" >> $GITHUB_ENV
fi

echo "✅ bandix apk 下载完成"
ls -lh */*.apk 2>/dev/null | cat
