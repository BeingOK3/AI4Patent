#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$ROOT/backend/.venv"
ENGINE_DIR="$ROOT/bin/opencode"
ENGINE="$ENGINE_DIR/opencode"

require_command() {
    command -v "$1" >/dev/null 2>&1 || {
        echo "缺少必要命令：$1" >&2
        exit 1
    }
}

require_command python3
require_command curl
require_command tar

case "$(uname -m)" in
    x86_64|amd64) arch="x64" ;;
    aarch64|arm64) arch="arm64" ;;
    *) echo "不支持的 Linux 架构：$(uname -m)" >&2; exit 1 ;;
esac

target="linux-$arch"
if [[ "$arch" == "x64" ]] && ! grep -qwi avx2 /proc/cpuinfo 2>/dev/null; then
    target+="-baseline"
fi
if [[ -f /etc/alpine-release ]] || (command -v ldd >/dev/null 2>&1 && ldd --version 2>&1 | grep -qi musl); then
    target+="-musl"
fi

mkdir -p "$ENGINE_DIR" "$ROOT/logs" "$ROOT/data/opencode" "$ROOT/workspace/uploads"

if [[ ! -x "$ENGINE" ]]; then
    archive="opencode-$target.tar.gz"
    url="${OPENCODE_DOWNLOAD_URL:-https://github.com/anomalyco/opencode/releases/latest/download/$archive}"
    temp_dir="$(mktemp -d)"
    trap 'rm -rf "$temp_dir"' EXIT

    echo "[1/4] 下载 OpenCode Linux 引擎 ($target)..."
    curl --fail --location --retry 3 --output "$temp_dir/$archive" "$url"
    tar -xzf "$temp_dir/$archive" -C "$temp_dir"
    install -m 755 "$temp_dir/opencode" "$ENGINE"
    echo "  ✓ OpenCode 已安装"
else
    echo "[1/4] OpenCode 已存在，跳过"
fi

if [[ ! -d "$VENV" ]]; then
    echo "[2/4] 创建 Python 虚拟环境..."
    python3 -m venv "$VENV"
fi
echo "[2/4] 安装 Python 依赖..."
"$VENV/bin/python" -m pip install --upgrade pip
"$VENV/bin/python" -m pip install -r "$ROOT/backend/requirements.txt"
echo "  ✓ 依赖已安装"

echo "[3/4] 运行目录已就绪"
if [[ -f "$ROOT/data/opencode/auth.json" ]]; then
    echo "[4/4] 已检测到 API 配置"
else
    echo "[4/4] 尚未配置 API Key；启动后在网页设置中填写即可"
fi

echo
echo "安装完成！"
echo "启动：./start.sh"
echo "开发：./dev.sh"
echo "停止：./stop.sh"
