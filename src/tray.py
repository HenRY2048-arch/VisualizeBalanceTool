"""系统托盘图标管理模块"""

import logging
from typing import TYPE_CHECKING

import pystray
from PIL import Image

from .icons import (
    balance_badge_spec,
    create_balance_badge_icon,
    create_no_key_icon,
    hex_to_rgb,
    quantize_water_level,
)

if TYPE_CHECKING:
    from .app import App

log = logging.getLogger(__name__)


class TrayManager:
    """管理 pystray 系统托盘图标"""

    def __init__(self, app: "App"):
        self.app = app
        self.icon: pystray.Icon | None = None
        self._no_key_img: Image.Image = create_no_key_icon()

        # 正常 = 徽标；告警/闪烁 = 同一枚徽标加红色描边
        # 缓存 (文字, 颜色, 水位, 模式) 避免重复生成图片
        self._badge_key: tuple[str, tuple] | None = None
        self._normal_img: Image.Image = create_balance_badge_icon(
            *balance_badge_spec(None), **self._appearance()
        )
        self._alert_img: Image.Image = create_balance_badge_icon(
            *balance_badge_spec(None), alert=True, **self._appearance()
        )
        self._current_img: Image.Image = self._normal_img

    # ------------------------------------------------------------------
    # 图标状态切换
    # ------------------------------------------------------------------

    def set_normal(self) -> None:
        self._update(self._normal_img)

    def set_alert(self) -> None:
        self._update(self._alert_img)

    def set_no_key(self) -> None:
        self._update(self._no_key_img)

    def set_balance(self, balance: float | None, apply: bool = True) -> None:
        """
        按最新余额刷新托盘图标（黑底 + 余额数字）。

        文字/颜色没有变化时复用同一张图片，避免每次轮询都重新分配内存。
        闪烁进行中不抢图标，交由闪烁逻辑控制。
        """
        cfg = self.app.cfg
        text, color, level = balance_badge_spec(
            balance,
            bands=cfg.get("badge_bands"),
            hundreds_bands=cfg.get("badge_hundreds_bands"),
            integer_color=cfg.get("badge_integer_color", "#FFFFFF"),
            water_unit=cfg.get("badge_water_unit", 1),
        )
        mode = cfg.get("badge_display_mode", "both")
        level = quantize_water_level(level)

        appearance = (
            str(cfg.get("badge_water_color", "#00BFFF")).upper(),
            int(cfg.get("badge_water_alpha", 72)),
            int(cfg.get("badge_text_alpha", 255)),
            str(cfg.get("badge_flash_color", "#FF3B30")).upper(),
            int(cfg.get("badge_flash_width", 8)),
        )
        key = (text, color, level, mode) + appearance
        if key != self._badge_key:
            self._badge_key = key
            kwargs = self._appearance()
            self._normal_img = create_balance_badge_icon(
                text, color, level, mode, **kwargs
            )
            self._alert_img = create_balance_badge_icon(
                text, color, level, mode, alert=True, **kwargs
            )
        if apply and not getattr(self.app, "_flashing", False):
            self._update(self._normal_img)

    def _appearance(self) -> dict:
        cfg = self.app.cfg
        return {
            "water_color": hex_to_rgb(cfg.get("badge_water_color", "#00BFFF")),
            "water_alpha": int(cfg.get("badge_water_alpha", 72)),
            "text_alpha": int(cfg.get("badge_text_alpha", 255)),
            "flash_color": hex_to_rgb(cfg.get("badge_flash_color", "#FF3B30")),
            "flash_width": int(cfg.get("badge_flash_width", 8)),
        }

    def _update(self, img: Image.Image) -> None:
        self._current_img = img
        if self.icon:
            try:
                self.icon.icon = img
            except Exception:
                log.debug("图标更新失败", exc_info=True)

    # ------------------------------------------------------------------
    # 托盘菜单
    # ------------------------------------------------------------------

    def _build_menu(self) -> pystray.Menu:
        sound_label = "关闭提示音" if self.app._sound_enabled else "开启提示音"
        return pystray.Menu(
            pystray.MenuItem(
                "立即刷新余额",
                lambda: self.app._on_manual_refresh(),
                default=True,
            ),
            pystray.MenuItem("设置…", lambda: self.app._on_open_settings()),
            pystray.MenuItem(sound_label, lambda: self.app._on_toggle_sound()),
            pystray.MenuItem(
                f"告警阈值: ¥{self.app.cfg.alert_threshold:.2f}",
                None,
                enabled=False,
            ),
            pystray.MenuItem("停止闪烁", lambda: self.app._on_stop_flash()),
            pystray.MenuItem("退出", lambda: self.app._on_exit()),
        )

    def rebuild_menu(self) -> None:
        if self.icon:
            self.icon.menu = self._build_menu()

    # ------------------------------------------------------------------
    # 启动 / 停止
    # ------------------------------------------------------------------

    def run(self) -> None:
        self.icon = pystray.Icon(
            name="visualize_balance",
            icon=self._current_img,
            title="VisualizeBalance — 加载中…",
            menu=self._build_menu(),
        )
        log.info("托盘图标已启动")
        self.icon.run()

    def stop(self) -> None:
        if self.icon:
            self.icon.stop()
