#!/bin/bash
# ============================================================
# 安装 WSL2 Codex 任务完成 Hook
#
# 目标 shell 判定顺序（永久策略，不再只看 .zshrc 是否存在）：
#   1. 环境变量 VB_SHELL（bash / zsh）—— 便于脚本化与测试
#   2. 登录 shell（getent passwd → $SHELL），且该 shell 必须真实可用
#   3. 兜底：优先 bash，其次 zsh，哪个装了用哪个
#   4. 都没有 → 打印手动安装说明并以非 0 退出
#
# 可选环境变量：
#   VB_SIGNAL_DIR   自定义信号目录（默认自动探测 Windows 用户目录）
#   VB_SHELL        强制指定 bash / zsh
#   VB_PURGE_STALE  设为 1 时自动清理装在“非目标 shell”里的旧 hook
# ============================================================

set -eu

echo "====================================="
echo "  安装 WSL2 Codex 任务完成 Hook"
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
        ""|*[!A-Za-z0-9._-]*) WIN_USER="" ;;   # 探测失败或输出异常，忽略
    esac

    if [ -n "$WIN_USER" ] && [ -d "/mnt/c/Users/$WIN_USER" ]; then
        SIGNAL_DIR="/mnt/c/Users/${WIN_USER}/.visualize_balance/signal"
    elif [ -n "${USER:-}" ] && [ -d "/mnt/c/Users/$USER" ]; then
        SIGNAL_DIR="/mnt/c/Users/${USER}/.visualize_balance/signal"
        echo "⚠ 无法通过 cmd.exe 探测 Windows 用户名，改用 \$USER: $SIGNAL_DIR"
    else
        echo "✗ 无法定位 Windows 用户目录。"
        echo "  请用 VB_SIGNAL_DIR 显式指定，例如："
        echo "    VB_SIGNAL_DIR=/mnt/c/Users/<你的Windows用户名>/.visualize_balance/signal bash scripts/install_wsl_hook.sh"
        exit 1
    fi
else
    SIGNAL_DIR="$VB_SIGNAL_DIR"
fi

echo "信号目录: $SIGNAL_DIR"
echo ""

mkdir -p "$SIGNAL_DIR" 2>/dev/null || true
if [ ! -d "$SIGNAL_DIR" ]; then
    echo "✗ 信号目录不可创建/不可写: $SIGNAL_DIR"
    exit 1
fi

# ------------------------------------------------------------------
# 2. 选择目标 shell
# ------------------------------------------------------------------
detect_login_shell() {
    local login=""
    if command -v getent >/dev/null 2>&1; then
        login=$(getent passwd "${USER:-$(id -un)}" 2>/dev/null | cut -d: -f7 || true)
    fi
    [ -z "$login" ] && login="${SHELL:-}"
    basename "${login:-}"
}

choose_shell() {
    local forced="${VB_SHELL:-}"
    local login
    login=$(detect_login_shell)

    # 1) 显式指定
    if [ -n "$forced" ]; then
        case "$forced" in
            bash|zsh) echo "$forced"; return ;;
            *) echo "✗ VB_SHELL 只支持 bash / zsh（收到: $forced）" >&2; echo ""; return ;;
        esac
    fi

    # 2) 登录 shell 优先，但必须真实可用
    case "$login" in
        zsh)
            if command -v zsh >/dev/null 2>&1; then echo "zsh"; return; fi
            echo "⚠ 登录 shell 是 zsh，但 zsh 未安装/不在 PATH，回退到 bash" >&2
            ;;
        bash)
            if command -v bash >/dev/null 2>&1; then echo "bash"; return; fi
            ;;
    esac

    # 3) 兜底：优先 bash
    if command -v bash >/dev/null 2>&1; then echo "bash"; return; fi
    if command -v zsh  >/dev/null 2>&1; then echo "zsh";  return; fi

    echo ""
}

SHELL_TYPE=$(choose_shell)
if [ -z "$SHELL_TYPE" ]; then
    echo "✗ 未找到可用的 bash 或 zsh，无法自动安装 hook。"
    echo "  请手动把下面的片段加入你的 shell 配置文件："
    echo ""
    echo '  _vb_last_cmd=""'
    echo '  _vb_capture_cmd() { case "$BASH_COMMAND" in _vb_*) return ;; esac; _vb_last_cmd="$BASH_COMMAND"; }'
    echo "  trap _vb_capture_cmd DEBUG"
    echo '  _vb_precmd_hook() {'
    echo '      if [[ "$_vb_last_cmd" == codex* || "$_vb_last_cmd" == "cx "* ]]; then'
    echo "          mkdir -p \"$SIGNAL_DIR\" 2>/dev/null"
    echo "          touch \"$SIGNAL_DIR/codex_complete.signal\" 2>/dev/null"
    echo '      fi'
    echo '      _vb_last_cmd=""'
    echo '  }'
    echo '  PROMPT_COMMAND="_vb_precmd_hook${PROMPT_COMMAND:+;$PROMPT_COMMAND}"'
    echo ""
    exit 1
fi

case "$SHELL_TYPE" in
    zsh)  RC_FILE="$HOME/.zshrc"  ;;
    bash) RC_FILE="$HOME/.bashrc" ;;
esac
if [ "$SHELL_TYPE" = "zsh" ]; then OTHER_RC="$HOME/.bashrc"; else OTHER_RC="$HOME/.zshrc"; fi

echo "登录 shell: $(detect_login_shell)"
echo "目标 shell: $SHELL_TYPE"
echo "目标配置文件: $RC_FILE"
echo ""

# ------------------------------------------------------------------
# 3. 清理装在非目标 shell 里的旧 hook（可选）
# ------------------------------------------------------------------
purge_hook_block() {
    local file="$1"
    [ -f "$file" ] || return 0
    grep -q "VisualizeBalance Codex Hook" "$file" 2>/dev/null || return 0
    awk '
        /# >>> VisualizeBalance Codex Hook >>>/ { skip = 1 }
        skip == 0 { print }
        /# <<< VisualizeBalance Codex Hook <<</ { skip = 0 }
    ' "$file" > "$file.vb_tmp" && mv "$file.vb_tmp" "$file"
}

if grep -q "VisualizeBalance Codex Hook" "$OTHER_RC" 2>/dev/null; then
    if [ "${VB_PURGE_STALE:-0}" = "1" ]; then
        purge_hook_block "$OTHER_RC"
        echo "✅ 已清理非目标 shell 中的旧 hook: $OTHER_RC"
    else
        echo "⚠ $OTHER_RC 里也有一份旧 hook，但当前目标 shell 是 $SHELL_TYPE。"
        echo "  那份 hook 永远不会执行，建议清理："
        echo "    VB_PURGE_STALE=1 bash $0"
    fi
    echo ""
fi

# ------------------------------------------------------------------
# 4. 安装（幂等）
# ------------------------------------------------------------------
if grep -q "VisualizeBalance Codex Hook" "$RC_FILE" 2>/dev/null; then
    echo "✅ $RC_FILE 中已存在 hook，跳过安装"
    echo ""
    echo "如需重装，请先删除 $RC_FILE 里"
    echo "'# >>> VisualizeBalance Codex Hook >>>' 与"
    echo "'# <<< VisualizeBalance Codex Hook <<<' 之间的内容。"
    exit 0
fi

if [ "$SHELL_TYPE" = "zsh" ]; then
    HOOK_CONTENT='
# >>> VisualizeBalance Codex Hook >>>
# Codex CLI 任务结束时，向 Windows 侧写入通知信号
_vb_codex_done=false
_vb_preexec() {
    [[ "$1" == codex* || "$1" == "cx "* ]] && _vb_codex_done=true
}
_vb_precmd() {
    if $_vb_codex_done; then
        _vb_codex_done=false
        local signal_dir="'"$SIGNAL_DIR"'"
        mkdir -p "$signal_dir" 2>/dev/null
        touch "$signal_dir/codex_complete.signal" 2>/dev/null
    fi
}
autoload -Uz add-zsh-hook 2>/dev/null && add-zsh-hook preexec _vb_preexec 2>/dev/null && add-zsh-hook precmd _vb_precmd 2>/dev/null
# <<< VisualizeBalance Codex Hook <<<
'
else
    HOOK_CONTENT='
# >>> VisualizeBalance Codex Hook >>>
# Codex CLI 任务结束时，向 Windows 侧写入通知信号
_vb_last_cmd=""
_vb_capture_cmd() {
    # 守卫：跳过本 hook 自己的命令。否则 DEBUG trap 会在 _vb_precmd_hook 被
    # 调用的瞬间把 _vb_last_cmd 覆盖成 "_vb_precmd_hook"，永远匹配不到 codex。
    case "$BASH_COMMAND" in _vb_*) return ;; esac
    _vb_last_cmd="$BASH_COMMAND"
}
trap _vb_capture_cmd DEBUG
_vb_precmd_hook() {
    if [[ "$_vb_last_cmd" == codex* || "$_vb_last_cmd" == "cx "* ]]; then
        local signal_dir="'"$SIGNAL_DIR"'"
        mkdir -p "$signal_dir" 2>/dev/null
        touch "$signal_dir/codex_complete.signal" 2>/dev/null
    fi
    _vb_last_cmd=""
}
# 用 ${VAR:-} 兜底，避免在 `set -u` 的 shell 里因 PROMPT_COMMAND 未定义报错
if [[ "${PROMPT_COMMAND:-}" != *"_vb_precmd_hook"* ]]; then
    PROMPT_COMMAND="_vb_precmd_hook${PROMPT_COMMAND:+;$PROMPT_COMMAND}"
fi
# <<< VisualizeBalance Codex Hook <<<
'
fi

echo "$HOOK_CONTENT" >> "$RC_FILE"
echo "✅ Hook 已安装到 $RC_FILE"
echo ""
echo "请执行以下命令使 hook 生效："
echo "  source $RC_FILE"
echo ""
echo "验证：新开终端运行 codex，退出后应看到信号文件出现："
echo "  ls -l \"$SIGNAL_DIR\""
echo "（Windows 端应用读取后会自动删除该文件）"
