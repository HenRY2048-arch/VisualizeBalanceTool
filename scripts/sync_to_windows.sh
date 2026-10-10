#!/bin/bash
# ============================================================
# 把 WSL 里的工作副本同步到 Windows 本地磁盘
#
# 为什么需要：Windows 侧如果在 \\wsl$\... 这类 UNC 路径下直接跑
# pip / PyInstaller，容易因为路径与文件锁的问题失败，所以先把源码
# 落到本地盘（D:\... ）再构建。
#
# 用法：
#   bash scripts/sync_to_windows.sh                        # 默认 -> /mnt/d/visualizeBalance
#   bash scripts/sync_to_windows.sh /mnt/e/vb              # 自定义目标
#   bash scripts/sync_to_windows.sh --force /mnt/d/other  # 目标不像本项目时强制同步
#
# 不会同步：.git、__pycache__、dist、build、*.spec、scripts/Output
# ============================================================

set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST=""
FORCE=0

for arg in "$@"; do
    case "$arg" in
        --force|-f) FORCE=1 ;;
        -h|--help)
            sed -n '2,15p' "$0" | sed 's/^# \{0,1\}//'
            exit 0
            ;;
        -*) echo "✗ 未知参数: $arg" >&2; exit 2 ;;
        *)  DEST="$arg" ;;
    esac
done
DEST="${DEST:-/mnt/d/visualizeBalance}"

echo "源目录  : $SRC"
echo "目标目录: $DEST"
echo

# ---- 安全检查：别把盘符根目录 / 系统目录当目标 ----
RESOLVED="$(realpath -m "$DEST")"
case "$RESOLVED" in
    /|/mnt|/mnt/c|/mnt/d|/mnt/e|/mnt/wsl|/home|/tmp|/usr|/etc|/var|/bin|/opt)
        echo "✗ 目标目录过于宽泛，拒绝同步（会把系统目录当项目目录处理）: $RESOLVED" >&2
        exit 1
        ;;
esac

# ---- 安全检查：目标非空时，必须看起来就是本项目 ----
if [ -d "$DEST" ] && [ -n "$(ls -A "$DEST" 2>/dev/null)" ] && [ ! -e "$DEST/run.py" ]; then
    if [ "$FORCE" -ne 1 ]; then
        echo "✗ $DEST 已存在、非空，且不像本项目（找不到 run.py）。" >&2
        echo "  为防误删已中止。确认无误请加 --force 重跑。" >&2
        exit 1
    fi
    echo "⚠ --force：忽略“目标不像本项目”的检查"
fi

mkdir -p "$DEST"

EXCLUDES=(
    --exclude=.git
    --exclude=.agents
    --exclude=.aws
    --exclude=.codex
    --exclude=.mcp
    --exclude=__pycache__
    --exclude=*.pyc
    --exclude=dist
    --exclude=build
    --exclude=*.spec
    --exclude=scripts/Output
)

if command -v rsync >/dev/null 2>&1; then
    # --delete 会清掉目标端已删除的源码文件；被 --exclude 命中的内容（dist/build 等）受保护
    rsync -a --delete "${EXCLUDES[@]}" "$SRC"/ "$DEST"/
else
    echo "⚠ 未找到 rsync，改用 tar 覆盖同步（不会删除目标端的多余文件）"
    tar -C "$SRC" \
        --exclude=.git --exclude=.agents --exclude=.aws --exclude=.codex \
        --exclude=.mcp --exclude=__pycache__ --exclude='*.pyc' \
        --exclude=dist --exclude=build --exclude='*.spec' \
        --exclude=scripts/Output \
        -cf - . | tar -C "$DEST" -xf -
fi

echo
echo "✅ 同步完成: $SRC  ->  $DEST"
echo
echo "接下来在 Windows PowerShell 里："
win_dest="$(echo "$DEST" | sed -E 's#^/mnt/([a-z])/#\U\1:/#; s#/#\\#g')"
echo "  cd $win_dest"
echo "  powershell -ExecutionPolicy Bypass -File scripts\\rebuild.ps1"
