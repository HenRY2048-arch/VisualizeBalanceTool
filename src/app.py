"""
VisualizeBalance 主应用模块
协调余额轮询、信号监听、通知、托盘图标的完整生命周期。
"""

import logging
import threading
import time

from . import __version__
from .config import Config
from .providers import get_provider, available_providers
from .providers.base import BalanceResult
from .notification import notify_balance_low, notify_task_complete
from .signal_monitor import check_signal, ensure_signal_dir
from .tray import TrayManager
from .settings import SettingsWindow

log = logging.getLogger(__name__)


class App:
    """应用主控类"""

    def __init__(self) -> None:
        self.cfg = Config()
        self.provider = None
        self._load_provider()

        # 状态
        self._last_balance: BalanceResult | None = None
        self._low_alerted: bool = False
        self._sound_enabled: bool = self.cfg.sound_enabled

        # 闪烁状态
        self._flashing: bool = False
        self._flash_timer: threading.Timer | None = None
        self._flash_counter: int = 0
        self._flash_lock = threading.Lock()

        # 停止事件
        self._stop_event = threading.Event()

        # 托盘管理器
        self.tray = TrayManager(self)

    # ==================================================================
    # 提供商管理
    # ==================================================================

    def _load_provider(self) -> None:
        try:
            self.provider = get_provider(self.cfg.provider)
            log.info("已加载提供商: %s", self.provider.display_name)
        except ValueError as exc:
            log.error("提供商加载失败: %s", exc)
            self.provider = None

    # ==================================================================
    # 生命周期
    # ==================================================================

    def run(self) -> None:
        """启动应用（阻塞，主线程运行托盘）"""
        log.info("VisualizeBalance v%s 启动中…", __version__)
        log.info("  提供商: %s", self.cfg.provider)
        log.info("  API URL: %s", self.provider.api_url if self.provider else "无")
        log.info("  API Key: %s", "已配置" if self.cfg.api_key else "⚠ 未配置")
        log.info("  告警阈值: ¥%.2f", self.cfg.alert_threshold)
        log.info("  轮询间隔: %ds", self.cfg.poll_interval)
        log.info("  信号目录: %s", self.cfg.signal_dir)

        ensure_signal_dir(self.cfg)

        if not self.cfg.api_key:
            self.tray.set_no_key()

        # 启动后台工作线程
        worker = threading.Thread(target=self._worker_loop, daemon=True)
        worker.start()

        # 主线程运行托盘（阻塞）
        self.tray.run()

    def _shutdown(self) -> None:
        log.info("正在退出…")
        self._stop_event.set()
        self._cancel_flash()
        self.tray.stop()

    # ==================================================================
    # 后台工作线程
    # ==================================================================

    def _worker_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._tick()
            except Exception:
                log.exception("工作线程异常")
            self._stop_event.wait(self.cfg.signal_poll_interval)

    def _tick(self) -> None:
        now = time.time()

        # 信号检查
        if check_signal(self.cfg):
            log.info("任务完成通知触发")
            notify_task_complete(sound=self._sound_enabled)
            self._start_flash()

        # 余额检查（按间隔）
        if not hasattr(self, "_last_poll"):
            self._last_poll = 0.0
        if now - self._last_poll >= self.cfg.poll_interval:
            self._last_poll = now
            self._poll_balance()

    def _poll_balance(self) -> None:
        if self.provider is None:
            self._update_title("无可用提供商")
            return

        result = self.provider.check(self.cfg.api_key)
        self._last_balance = result

        if not result.ok:
            log.warning("余额查询失败: %s", result.error)
            self._update_title("查询失败")
            return

        balance = result.balance
        assert balance is not None

        status = "可用" if result.is_available else "不可用"
        detail = f"赠送: ¥{result.granted:.2f}  充值: ¥{result.topped_up:.2f}"
        self._update_title(f"余额: ¥{balance:.2f} ({status}) | {detail}")
        # 托盘图标显示为黑底余额数字（颜色随零头变化）
        self.tray.set_balance(balance)
        log.info(
            "余额: ¥%.2f  可用=%s  赠送=¥%.2f  充值=¥%.2f",
            balance, result.is_available, result.granted, result.topped_up,
        )

        threshold = self.cfg.alert_threshold
        if balance < threshold:
            self.tray.set_alert()
            if not self._low_alerted:
                self._low_alerted = True
                log.warning("余额不足！当前 ¥%.2f < 阈值 ¥%.2f", balance, threshold)
                notify_balance_low(balance, sound=self._sound_enabled)
                self._start_flash()
        else:
            self._low_alerted = False
            if not self._flashing:
                self.tray.set_normal()

    # ==================================================================
    # 托盘提示文字
    # ==================================================================

    def _update_title(self, text: str) -> None:
        if self.tray.icon:
            try:
                self.tray.icon.title = f"VisualizeBalance — {text}"
            except Exception:
                pass

    # ==================================================================
    # 图标闪烁
    # ==================================================================

    def _start_flash(self) -> None:
        max_ticks = self.cfg.flash_timeout // self.cfg.flash_interval
        with self._flash_lock:
            if self._flashing:
                self._flash_counter = 0
                return
            self._flashing = True
            self._flash_counter = 0
            self._max_flash_ticks = max_ticks
        self._schedule_flash_tick()

    def _cancel_flash(self) -> None:
        with self._flash_lock:
            self._flashing = False
            if self._flash_timer:
                self._flash_timer.cancel()
                self._flash_timer = None
        self._restore_icon()

    def _restore_icon(self) -> None:
        if self._last_balance and self._last_balance.ok:
            if self._last_balance.balance < self.cfg.alert_threshold:
                self.tray.set_alert()
                return
        self.tray.set_normal()

    def _schedule_flash_tick(self) -> None:
        self._flash_timer = threading.Timer(
            self.cfg.flash_interval / 1000.0, self._flash_tick
        )
        self._flash_timer.daemon = True
        self._flash_timer.start()

    def _flash_tick(self) -> None:
        with self._flash_lock:
            if not self._flashing:
                return
            self._flash_counter += 1
            if self._flash_counter > self._max_flash_ticks:
                self._flashing = False
                self._flash_timer = None
                self._restore_icon()
                return

        if self.tray._current_img is self.tray._normal_img:
            self.tray.set_alert()
        else:
            self.tray.set_normal()
        self._schedule_flash_tick()

    # ==================================================================
    # 托盘菜单回调
    # ==================================================================

    def _on_manual_refresh(self) -> None:
        log.info("手动刷新余额…")
        threading.Thread(target=self._poll_balance, daemon=True).start()

    def _on_stop_flash(self) -> None:
        log.info("手动停止闪烁")
        self._cancel_flash()

    def _on_open_settings(self) -> None:
        """打开设置窗口（通过 tk 的 after 机制在主线程执行）"""
        def _open():
            def _on_saved():
                self.cfg.reload()
                self._load_provider()
                self._sound_enabled = self.cfg.sound_enabled
                # 阈值可能变了，立刻按当前余额重绘一次徽标
                if self._last_balance and self._last_balance.ok:
                    self.tray.set_balance(self._last_balance.balance)
                log.info("配置已重新加载")
            SettingsWindow(self.cfg).show(on_saved=_on_saved)

        if self.tray.icon:
            self.tray.icon.visible = True  # 确保主线程事件循环活跃
        # 通过 Timer 在新线程中打开（tkinter 需要独立事件循环）
        threading.Thread(target=_open, daemon=True).start()

    def _on_toggle_sound(self) -> None:
        """切换提示音开关"""
        self._sound_enabled = not self._sound_enabled
        self.cfg.set("sound_enabled", self._sound_enabled)
        self.cfg.save()
        state = "开启" if self._sound_enabled else "关闭"
        log.info("提示音已%s", state)
        self.tray.rebuild_menu()

    def _on_exit(self) -> None:
        self._shutdown()
