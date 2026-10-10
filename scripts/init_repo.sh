#!/bin/bash
# ============================================================
# 把本项目初始化为 git 仓库并完成首次提交（在 WSL 里运行）
#
# 用法：
#   bash scripts/init_repo.sh
#   bash scripts/init_repo.sh --remote git@github.com:USER/visualizeBalance.git
#
# 步骤：
#   1. 清理工具沙箱可能留下的只读空 .git 占位目录
#   2. git init -b main
#   3. git add -A + 首次提交
#   4. 可选：设置 origin
# ============================================================

set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

REMOTE=""
while [ $# -gt 0 ]; do
    case "$1" in
        --remote)
            REMOTE="${2:-}"
            if [ -z "$REMOTE" ]; then
                echo "✗ --remote 后面要跟仓库地址" >&2
                exit 2
            fi
            shift 2
            ;;
        -h|--help)
            sed -n '2,13p' "$0" | sed 's/^# \{0,1\}//'
            exit 0
            ;;
        *)
            echo "✗ 未知参数: $1" >&2
            exit 2
            ;;
    esac
done

echo "项目目录: $(pwd)"
echo

# ------------------------------------------------------------------
# 1. 只读空 .git 占位目录（工具沙箱产物）
# ------------------------------------------------------------------
if [ -e .git ] && [ ! -e .git/HEAD ]; then
    echo "检测到没有 HEAD 的 .git，尝试移除…"
    if rmdir .git 2>/dev/null; then
        echo "  已移除"
    elif [ -d .git ]; then
        cat >&2 <<'EOF'
✗ 无法移除 .git —— 它多半是一个只读挂载。

  这是 Codex 之类工具在当前会话里挂上的只读 tmpfs，用下面命令确认：

      mount | grep visualizeBalance

  如果是这样，在你自己的 WSL 终端窗口里执行（不是通过工具）：

      sudo umount .git 2>/dev/null; rmdir .git

  然后再重跑本脚本。
EOF
        exit 1
    fi
fi

# ------------------------------------------------------------------
# 2. git init
# ------------------------------------------------------------------
if git rev-parse --git-dir >/dev/null 2>&1; then
    echo "已经是 git 仓库，跳过 git init"
else
    git init -b main
fi

# ------------------------------------------------------------------
# 3. 身份（已配置全局身份则不动）
# ------------------------------------------------------------------
if ! git config user.email >/dev/null 2>&1; then
    echo "⚠ git 未配置 user.email，写入仓库级默认值（以后可改）"
    git config user.name  "VisualizeBalance"
    git config user.email "visualizebalance@users.noreply.github.com"
fi

# ------------------------------------------------------------------
# 4. add + 首次提交
# ------------------------------------------------------------------
git add -A

echo
echo "将要提交的文件："
git status --short
echo

if git rev-parse --verify HEAD >/dev/null 2>&1; then
    echo "已有提交（$(git rev-parse --short HEAD)），跳过首次提交"
    echo "后续提交请用：git add -A && git commit -m \"...\""
elif git diff --cached --quiet; then
    echo "没有需要提交的内容"
else
    git commit -q -m "初始提交：VisualizeBalance v1.1.0"
    echo "✅ 首次提交完成：$(git rev-parse --short HEAD)"
fi

# ------------------------------------------------------------------
# 5. remote
# ------------------------------------------------------------------
if [ -n "$REMOTE" ]; then
    if git remote get-url origin >/dev/null 2>&1; then
        git remote set-url origin "$REMOTE"
    else
        git remote add origin "$REMOTE"
    fi
    echo "✅ 已设置 origin = $REMOTE"
fi

echo
echo "接下来（远端仓库：HenRY2048-arch/VisualizeBalanceTool）："
if [ -n "$REMOTE" ]; then
    echo "  1) 推送："
    echo "       git push -u origin main"
else
    echo "  1) 关联远端并推送："
    echo "       git remote add origin git@github.com:HenRY2048-arch/VisualizeBalanceTool.git"
    echo "       git push -u origin main"
fi
echo
echo "  如果报 'updates were rejected ... fetch first'："
echo "  远端建仓时自动生成过 README，和本地是两条无关历史。二选一："
echo
echo "    a) 合并（保留本仓库内容，冲突时选本地 README）"
echo "         git pull origin main --allow-unrelated-histories --no-rebase"
echo "         git add -A && git commit -m \"合并远端 README\""
echo "         git push -u origin main"
echo
echo "    b) 直接覆盖（确认远端那个自动生成的 README 不需要）"
echo "         git push -u origin main --force"
