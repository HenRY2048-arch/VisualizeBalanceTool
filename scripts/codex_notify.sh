#!/bin/bash
# ============================================================
# VisualizeBalance — Codex CLI 回合结束钩子
#
# 由 ~/.codex/config.toml 里的
#     notify = ["bash", "<安装后的本脚本路径>"]
# 调用。Codex 会把一个 JSON 作为参数传进来。
#
# 注意：部分 Codex 版本会在「回合刚开始」也回调一次。所以这里不只看
# 有没有被调用，还要确认：
#   1. 事件类型是 agent-turn-complete
#   2. last-assistant-message 存在且非空（说明确实已经产出内容）
#   3. 同一个 turn-id 只通知一次
#
# 每次调用都会记到 ~/.visualize_balance/notify.log（保留最近 200 行），
# 方便排查"为什么早了/为什么没来"。
#
# 任何异常都不应影响 Codex，因此永远 exit 0。
# ============================================================

set +e

DEFAULT_SIGNAL_DIR="__VB_SIGNAL_DIR__"
case "$DEFAULT_SIGNAL_DIR" in
    __VB_*) DEFAULT_SIGNAL_DIR="$HOME/.visualize_balance/signal" ;;
esac

SIGNAL_DIR="${VB_SIGNAL_DIR:-$DEFAULT_SIGNAL_DIR}"
STATE_DIR="$HOME/.visualize_balance"
LOG_FILE="$STATE_DIR/notify.log"

mkdir -p "$SIGNAL_DIR" "$STATE_DIR" 2>/dev/null

PAYLOAD="${1:-}"

# ------------------------------------------------------------------
# 0. 记录调用（便于诊断）
# ------------------------------------------------------------------
if [ -n "$PAYLOAD" ]; then
    printf '%s\t%s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$PAYLOAD" >> "$LOG_FILE" 2>/dev/null
    tail -n 200 "$LOG_FILE" > "$LOG_FILE.tmp" 2>/dev/null \
        && mv "$LOG_FILE.tmp" "$LOG_FILE" 2>/dev/null
fi

# 某些旧版本可能不传 payload；无法判断时按旧行为通知，并记录警告
if [ -z "$PAYLOAD" ]; then
    printf '%s\n' "warn: empty payload, firing anyway" >> "$LOG_FILE" 2>/dev/null
    : > "$SIGNAL_DIR/codex_complete.signal" 2>/dev/null
    exit 0
fi

# ------------------------------------------------------------------
# 1. 只接受回合完成事件（兼容旧版 agent-turn-complete 与新版 turn-complete）
# ------------------------------------------------------------------
case "$PAYLOAD" in
    *agent-turn-complete*) ;;
    *'"type":"turn-complete"'*) ;;
    *'"type": "turn-complete"'*) ;;
    *) exit 0 ;;
esac

# ------------------------------------------------------------------
# 2. 内部回合（线程标题生成 / 会话摘要）不算用户任务完成
#
# 实测 Codex 会在用户消息前后额外触发：
#   - "Generate a concise, single-line task title ..."  标题生成
#   - "Write a brief catch-up for a user ..."           会话摘要
# 这些回合的 last-assistant-message 非空、turn-id 也各不相同，仅靠
# “消息非空”无法过滤，必须按内部提示词特征跳过。
# ------------------------------------------------------------------
case "$PAYLOAD" in
    *"single-line task title"*|*"catch-up for a user"*|*"Return JSON with summary"*)
        printf '%s\n' "skip: internal turn (title/recap)" >> "$LOG_FILE" 2>/dev/null
        exit 0
        ;;
esac

# ------------------------------------------------------------------
# 3. 必须有非空的助手输出，否则说明回合才刚开始
# ------------------------------------------------------------------
case "$PAYLOAD" in
    *'"last-assistant-message": ""'*|*'"last-assistant-message":""'*)
        printf '%s\n' "skip: assistant message empty" >> "$LOG_FILE" 2>/dev/null
        exit 0
        ;;
esac
printf '%s' "$PAYLOAD" | grep -q '"last-assistant-message"' || {
    printf '%s\n' "skip: no assistant message field" >> "$LOG_FILE" 2>/dev/null
    exit 0
}

# ------------------------------------------------------------------
# 3. 同一个 turn-id 只通知一次
# ------------------------------------------------------------------
TURN_ID=$(printf '%s' "$PAYLOAD" \
    | sed -n 's/.*"turn-id"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')
if [ -n "$TURN_ID" ]; then
    LAST_FILE="$STATE_DIR/.last_turn_id"
    if [ -f "$LAST_FILE" ] && [ "$(cat "$LAST_FILE" 2>/dev/null)" = "$TURN_ID" ]; then
        printf '%s\n' "skip: duplicate turn $TURN_ID" >> "$LOG_FILE" 2>/dev/null
        exit 0
    fi
    printf '%s' "$TURN_ID" > "$LAST_FILE" 2>/dev/null
fi

# ------------------------------------------------------------------
# 4. 写信号
# ------------------------------------------------------------------
: > "$SIGNAL_DIR/codex_complete.signal" 2>/dev/null
printf '%s\n' "signal written (turn=$TURN_ID)" >> "$LOG_FILE" 2>/dev/null

exit 0
