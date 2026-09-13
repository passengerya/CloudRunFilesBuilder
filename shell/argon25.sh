#!/bin/bash

set -euo pipefail

# 平台基础URL (25.12 起 ImmortalWrt 改用 apk 包管理, 官方源: downloads.immortalwrt.org)
declare -A PLATFORMS=(
  ["x86_64"]="https://downloads.immortalwrt.org/releases/25.12.2/packages/x86_64"
  ["aarch64_generic"]="https://downloads.immortalwrt.org/releases/25.12.2/packages/aarch64_generic"
  ["aarch64_cortex-a53"]="https://downloads.immortalwrt.org/releases/25.12.2/packages/aarch64_cortex-a53"
)

# 各包所在 Feed
declare -A PACKAGE_SOURCES=(
  ["luci-theme-argon"]="luci"
  ["luci-app-argon-config"]="luci"
  ["luci-i18n-argon-config-zh-cn"]="luci"
)

OUT_DIR="$(pwd)"
TMP_DIR="$(mktemp -d)"

cleanup() {
    rm -rf "$TMP_DIR"
}
trap cleanup EXIT


for platform in "${!PLATFORMS[@]}"; do

    BASE_URL="${PLATFORMS[$platform]}"
    SAVE_DIR="${OUT_DIR}/${platform}"
    mkdir -p "$SAVE_DIR"

    echo
    echo "📦 Platform: $platform"

    for pkg in "${!PACKAGE_SOURCES[@]}"; do

        feed="${PACKAGE_SOURCES[$pkg]}"
        URL="${BASE_URL}/${feed}"
        INDEX="${TMP_DIR}/${platform}_${feed}.json"

        echo "🔍 Checking ${pkg}"

        # 下载 index.json（每个 feed 只下载一次）
        if [[ ! -f "$INDEX" ]]; then
            echo "🌐 Fetching ${feed} index..."
            if ! curl -fsSL "${URL}/index.json" -o "$INDEX"; then
                echo "❌ Failed to fetch index.json"
                continue
            fi
        fi

        # 从 index.json 获取版本号
        VERSION=$(
            grep -oP "\"${pkg}\":\\s*\"\\K[^\"]+" "$INDEX" || true
        )

        if [[ -z "$VERSION" ]]; then
            echo "❌ ${pkg} not found"
            continue
        fi

        FILE="${pkg}-${VERSION}.apk"

        echo "⬇️  ${FILE}"
        echo "⬇️  ${URL}"

        if curl -fsSL \
            -o "${SAVE_DIR}/${FILE}" \
            "${URL}/${FILE}"; then
            echo "   ✔ OK"
        else
            echo "   ❌ Download failed"
        fi

    done

done

echo
echo "✅ 25.12.x Argon packages downloaded."
