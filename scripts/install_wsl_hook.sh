#!/bin/bash
# ============================================================
# 安装 VisualizeBalance 的 Codex 回合结束钩子（WSL2 侧）
#
# 方案：使用 Codex CLI 的 notify 配置，在**每次 AI 回合结束**时写信号文件。
# 旧的 shell preexec/precmd 方案只有在退出 codex 进程（如 /exit）时才触发，
# 已废弃：本脚本会自动把 ~/.bashrc / ~/.zshrc 里的旧 hook 清掉。
#
# 可选环境变量：
#   VB_SIGNAL_DIR   自定义信号目录（默认自动探测 Windows 用户目录）
#   CODEX_HOME      默认 ~/.codex
# ============================================================

set -eu

echo "====================================="
echo "  安装 Codex 回合结束钩子"
echo "====================================="
echo ""

# ------------------------------------------------------------------
# 1. 探测 Windows 侧信号目录
# ------------------------------------------------------------------
if [ -z "${VB_SIGNAL_DIR:-}" ]; then
    WIN_USER=""
    if command -v cmd.exe >/dev/null 2>&1; then
        WIN_USER=$(cmd.exe /c "echo %USERNAME%" 2>/dev/null | tr -d '\r' | tr -d '[:space:]' || true)
    fi
    case "$WIN_USER" in
        ""|*[!A-Za-z0-9._-]*) WIN_USER="" ;;
    esac

    if [ -n "$WIN_USER" ] && [ -d "/mnt/c/Users/$WIN_USER" ]; then
        SIGNAL_DIR="/mnt/c/Users/${WIN_USER}/.visualize_balance/signal"
    elif [ -n "${USER:-}" ] && [ -d "/mnt/c/Users/$USER" ]; then
        SIGNAL_DIR="/mnt/c/Users/${USER}/.visualize_balance/signal"
        echo "⚠ 无法通过 cmd.exe 探测 Windows 用户名，改用 \$USER: $SIGNAL_DIR"
    else
        echo "✗ 无法定位 Windows 用户目录。"
        echo "  请用 VB_SIGNAL_DIR 显式指定，例如："
        echo "    VB_SIGNAL_DIR=/mnt/c/Users/<Windows用户名>/.visualize_balance/signal bash scripts/install_wsl_hook.sh"
        exit 1
    fi
else
    SIGNAL_DIR="$VB_SIGNAL_DIR"
fi

echo "信号目录: $SIGNAL_DIR"
mkdir -p "$SIGNAL_DIR" 2>/dev/null || true
if [ ! -d "$SIGNAL_DIR" ]; then
    echo "✗ 信号目录不可创建: $SIGNAL_DIR"
    exit 1
fi

# ------------------------------------------------------------------
# 2. 安装 notify 脚本到固定位置
# ------------------------------------------------------------------
SRC_SCRIPT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/codex_notify.sh"
if [ ! -f "$SRC_SCRIPT" ]; then
    echo "✗ 找不到 $SRC_SCRIPT"
    exit 1
fi

INSTALL_DIR="$HOME/.visualize_balance"
NOTIFY_SCRIPT="$INSTALL_DIR/codex_notify.sh"
mkdir -p "$INSTALL_DIR"

sed "s#__VB_SIGNAL_DIR__#$SIGNAL_DIR#" "$SRC_SCRIPT" > "$NOTIFY_SCRIPT"
chmod 755 "$NOTIFY_SCRIPT"
echo "通知脚本: $NOTIFY_SCRIPT"

# 自检可写性。用临时文件名，避免在应用运行时误触发一次“任务完成”通知。
SELFTEST="$SIGNAL_DIR/.vb_selftest"
if : > "$SELFTEST" 2>/dev/null; then
    rm -f "$SELFTEST"
    echo "✅ 信号目录可写"
else
    echo "⚠ 信号目录不可写，请检查 $SIGNAL_DIR"
fi

# ------------------------------------------------------------------
# 3. 写入 Codex 的 notify 配置
# ------------------------------------------------------------------
CODEX_HOME_DIR="${CODEX_HOME:-$HOME/.codex}"
CONFIG="$CODEX_HOME_DIR/config.toml"
NOTIFY_LINE="notify = [\"bash\", \"$NOTIFY_SCRIPT\"]"

mkdir -p "$CODEX_HOME_DIR"
[ -f "$CONFIG" ] || : > "$CONFIG"

echo "Codex 配置: $CONFIG"

if grep -qE '^[[:space:]]*notify[[:space:]]*=' "$CONFIG"; then
    EXISTING=$(grep -E '^[[:space:]]*notify[[:space:]]*=' "$CONFIG" | head -1)
    case "$EXISTING" in
        *"$NOTIFY_SCRIPT"*)
            echo "✅ notify 已指向本脚本，无需修改"
            ;;
        *)
            echo "⚠ config.toml 里已经有别的 notify 配置，未覆盖："
            echo "    $EXISTING"
            echo "  如需改用本脚本，请手动改成："
            echo "    $NOTIFY_LINE"
            ;;
    esac
else
    cp "$CONFIG" "$CONFIG.vb_bak" 2>/dev/null || true
    # 顶层键必须写在第一个 [table] 之前，否则会被解析进某个表里
    awk -v line="$NOTIFY_LINE" '
        BEGIN { done = 0 }
        !done && /^[[:space:]]*\[/ { print line; done = 1 }
        { print }
        END { if (!done) print line }
    ' "$CONFIG" > "$CONFIG.vb_tmp" && mv "$CONFIG.vb_tmp" "$CONFIG"
    echo "✅ 已写入: $NOTIFY_LINE"
    echo "   （原配置备份: $CONFIG.vb_bak）"
fi

# ------------------------------------------------------------------
# 4. 清理旧 shell hook（只在退出 codex 时触发，已废弃）
# ------------------------------------------------------------------
remove_legacy_hook() {
    local file="$1"
    [ -f "$file" ] || return 0
    grep -q "VisualizeBalance Codex Hook" "$file" 2>/dev/null || return 0
    cp "$file" "$file.vb_bak" 2>/dev/null || true
    awk '
        /# >>> VisualizeBalance Codex Hook >>>/ { skip = 1 }
        skip == 0 { print }
        /# <<< VisualizeBalance Codex Hook <<</ { skip = 0 }
    ' "$file" > "$file.vb_tmp" && mv "$file.vb_tmp" "$file"
    echo "🧹 已移除旧 shell hook: $file（备份: $file.vb_bak）"
}

remove_legacy_hook "$HOME/.bashrc"
remove_legacy_hook "$HOME/.zshrc"

echo ""
echo "完成。用法："
echo "  - 不需要重开终端；下次启动 codex 时会读取 notify 配置"
echo "  - 让 Codex 回答任意一句话（不用 /exit），Windows 托盘应立刻闪动 + 响铃"
echo ""
echo "自检："
echo "  grep '^notify' \"$CONFIG\""
echo "  ls -l \"$SIGNAL_DIR\"     # 应用读取后会自动删除信号文件"
