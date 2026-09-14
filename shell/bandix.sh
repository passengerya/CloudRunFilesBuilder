#!/bin/bash
set -e

# 下载 bandix 各平台 ipk:
# - bandix 主程序 + luci-app-bandix 来自 dl.openwrt.ai/kiddin9
# - luci-i18n-bandix-zh-cn 来自 timsaya/luci-app-bandix 的 GitHub Release

declare -A PLATFORMS=(
  ["x86"]="x86_64"
  ["arm64"]="aarch64_generic"
  ["a53"]="aarch64_cortex-a53"
)

mkdir -p x86 arm64 a53

# i18n (all 架构, 从 GitHub Release 取)
I18N_URL=$(curl -s -H "Authorization: token ${GITHUB_TOKEN:-}" \
  https://api.github.com/repos/timsaya/luci-app-bandix/releases \
  | jq -r 'map(select(.prerelease==false)) | sort_by(.published_at) | last
           | .assets[] | select(.name | test("^luci-i18n-bandix-zh-cn_.*\\.ipk$")) | .browser_download_url')

for dir in "${!PLATFORMS[@]}"; do
  arch="${PLATFORMS[$dir]}"
  BASE_URL="https://dl.openwrt.ai/packages-24.10/${arch}/kiddin9/"
  echo "[+] 获取 ${dir} (${arch}) 目录列表..."

  page=$(curl -sL --max-time 60 "$BASE_URL")

  # bandix 主程序(排除 luci-app-bandix)
  BANDIX_IPK=$(echo "$page" | grep -oP 'href="\K[^"]*bandix_[^"]+\.ipk' | grep -v 'luci-app-bandix' | head -n1)
  # luci 界面
  LUCI_IPK=$(echo "$page" | grep -oP 'href="\K[^"]*luci-app-bandix_[^"]+\.ipk' | head -n1)

  for ipk in "$BANDIX_IPK" "$LUCI_IPK"; do
    if [ -n "$ipk" ]; then
      echo "[+] 下载 $ipk"
      curl -sL --max-time 300 -o "${dir}/${ipk}" "${BASE_URL}${ipk}"
    else
      echo "[!] 未找到 ${arch} 的 bandix ipk"
    fi
  done

  # i18n 每个平台目录都放一份
  if [ -n "$I18N_URL" ]; then
    I18N_NAME=$(basename "$I18N_URL")
    echo "[+] 下载 $I18N_NAME"
    curl -sL --max-time 120 -o "${dir}/${I18N_NAME}" "$I18N_URL" || echo "[!] i18n 下载失败"
  else
    echo "[!] 未找到 luci-i18n-bandix-zh-cn 资产"
  fi
done

# 提取版本号(取 x86 的 bandix ipk 文件名, 如 bandix_0.11.0-r25_x86_64.ipk -> 0.11.0-r25)
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
