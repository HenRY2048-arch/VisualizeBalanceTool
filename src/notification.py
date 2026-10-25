"""通知引擎 — 声音 + Windows Toast 弹窗"""

import logging
import sys
from pathlib import Path

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 声音播放
# ---------------------------------------------------------------------------

_KNOCK_WAV: Path | None = None


def _assets_dir() -> Path:
    if getattr(sys, "_MEIPASS", None):
        return Path(sys._MEIPASS) / "assets"
    return Path(__file__).resolve().parent.parent / "assets"


def _resolve_wav() -> Path | None:
    """查找自定义 knock.wav，不存在则返回 None"""
    candidates = [
        _assets_dir() / "knock.wav",
        Path.home() / ".visualize_balance" / "knock.wav",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def play_sound() -> None:
    """播放通知音效"""
    global _KNOCK_WAV
    if _KNOCK_WAV is None:
        _KNOCK_WAV = _resolve_wav()

    if _KNOCK_WAV:
        try:
            import winsound
            winsound.PlaySound(str(_KNOCK_WAV), winsound.SND_FILENAME | winsound.SND_ASYNC)
            return
        except Exception as exc:
            log.debug("WAV 播放失败: %s，降级为系统提示音", exc)

    try:
        import winsound
        winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
    except Exception:
        log.debug("系统提示音播放失败（非 Windows 环境？）")


# ---------------------------------------------------------------------------
# Windows Toast 通知
# ---------------------------------------------------------------------------


def send_toast(title: str, message: str) -> None:
    """发送 Windows 10/11 Toast 通知"""
    try:
        from winotify import Notification, audio
        toast = Notification(
            app_id="VisualizeBalance",
            title=title,
            msg=message,
            duration="short",
        )
        toast.set_audio(audio.Default, loop=False)
        toast.show()
    except ImportError:
        log.warning("winotify 未安装，Toast 通知不可用")
    except Exception as exc:
        log.warning("Toast 发送失败: %s", exc)


# ---------------------------------------------------------------------------
# 组合通知
# ---------------------------------------------------------------------------


def notify_task_complete(sound: bool = True, toast: bool = True) -> None:
    """任务完成通知（声音与 Toast 可分别开关）"""
    if sound:
        play_sound()
    if toast:
        send_toast("Codex 任务完成", "你的 AI 任务已完成，请查看结果。")


def notify_balance_low(balance: float, sound: bool = True, symbol: str = "¥") -> None:
    """余额不足告警"""
    if sound:
        play_sound()
    send_toast("余额不足告警", f"当前余额仅剩 {symbol}{balance:.2f}，请及时充值！")
