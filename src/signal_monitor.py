"""WSL2 信号文件监听模块"""

import logging
from pathlib import Path

log = logging.getLogger(__name__)

SIGNAL_FILE = "codex_complete.signal"


def _get_signal_path(cfg) -> Path:
    return cfg.signal_dir / SIGNAL_FILE


def check_signal(cfg) -> bool:
    """
    检查信号文件是否存在。
    存在则删除并返回 True。
    """
    path = _get_signal_path(cfg)
    if path.exists():
        try:
            path.unlink()
            log.info("收到 Codex 任务完成信号")
            return True
        except OSError as exc:
            log.warning("删除信号文件失败: %s", exc)
            return True
    return False


def ensure_signal_dir(cfg) -> None:
    cfg.signal_dir.mkdir(parents=True, exist_ok=True)
    log.info("信号目录: %s", cfg.signal_dir)
