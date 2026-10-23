"""设置窗口 — tkinter 实现，用于可视化配置 API Key 等参数"""

import logging
import os
import re
import sys
import tkinter as tk
import winreg
from tkinter import colorchooser, messagebox, ttk
from pathlib import Path

from .config import Config

log = logging.getLogger(__name__)

_PROVIDER_OPTIONS = ["deepseek", "openai"]

_MODE_LABELS = {
    "both": "数字 + 水位",
    "number": "仅数字",
    "water": "仅水位",
}
_MODE_KEYS = {label: key for key, label in _MODE_LABELS.items()}

_HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
_MAX_FRACTION_BANDS = 10
_MAX_HUNDREDS_BANDS = 20


def _get_exe_path() -> str:
    if getattr(sys, "frozen", False):
        return sys.executable
    return str(Path(__file__).resolve().parent.parent / "run.py")


class BandEditor(ttk.Frame):
    """
    颜色分段编辑器。

    每行：起始值输入框 + 颜色按钮（点击打开色盘）+ 删除按钮。
    通过 set_bands / get_bands 读写，数据格式为 [{"at": float, "color": "#RRGGBB"}]。
    """

    def __init__(self, master) -> None:
        super().__init__(master)
        self.rows: list[dict] = []
        self.limit = _MAX_FRACTION_BANDS
        self.step = 0.1
        self.max_at = 1.0

        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self.canvas = tk.Canvas(self, height=150, highlightthickness=0, borderwidth=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.scrollbar.grid(row=0, column=1, sticky="ns")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.inner = ttk.Frame(self.canvas)
        self._window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", self._sync_scrollregion)
        self.canvas.bind("<Configure>", self._sync_width)

        footer = ttk.Frame(self)
        footer.grid(row=1, column=0, columnspan=2, sticky="w", pady=(6, 0))
        self.add_button = ttk.Button(footer, text="添加一段", command=self.add_row)
        self.add_button.pack(side="left")
        self.count_label = ttk.Label(footer, text="", foreground="gray")
        self.count_label.pack(side="left", padx=(10, 0))

    # ------------------------------------------------------------------

    def _sync_scrollregion(self, _event=None) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _sync_width(self, event) -> None:
        self.canvas.itemconfigure(self._window, width=event.width)

    def set_limit(self, limit: int, step: float = 0.1, max_at: float = 1.0) -> None:
        self.limit = limit
        self.step = step
        self.max_at = max_at
        self._refresh_footer()

    def set_bands(self, bands) -> None:
        for row in self.rows:
            row["frame"].destroy()
        self.rows = []
        for band in bands or []:
            self._append_row(band.get("at"), band.get("color", "#FFFFFF"))
        self._refresh_footer()

    def _append_row(self, at, color) -> None:
        if len(self.rows) >= self.limit:
            return

        frame = ttk.Frame(self.inner)
        frame.pack(fill="x", pady=2)

        value = "" if at is None else f"{float(at):g}"
        at_var = tk.StringVar(value=value)

        ttk.Label(frame, text="大于等于").pack(side="left")
        ttk.Entry(frame, textvariable=at_var, width=8).pack(side="left", padx=(4, 10))

        row = {"frame": frame, "at": at_var, "color": str(color), "swatch": None}

        def pick_color() -> None:
            _rgb, chosen = colorchooser.askcolor(
                color=row["color"], parent=self, title="选择数字颜色"
            )
            if chosen:
                row["color"] = chosen.upper()
                row["swatch"].configure(bg=row["color"])

        swatch = tk.Button(
            frame, text="    ", width=4, bg=row["color"],
            relief="raised", command=pick_color,
        )
        swatch.pack(side="left", padx=(0, 8))
        row["swatch"] = swatch

        ttk.Button(
            frame, text="删除", width=6,
            command=lambda: self._remove_row(row),
        ).pack(side="left")

        self.rows.append(row)
        self._refresh_footer()

    def _remove_row(self, row) -> None:
        if len(self.rows) <= 1:
            return
        row["frame"].destroy()
        self.rows.remove(row)
        self._refresh_footer()

    def add_row(self) -> None:
        if len(self.rows) >= self.limit:
            return
        last = 0.0
        if self.rows:
            try:
                last = float(self.rows[-1]["at"].get())
            except ValueError:
                last = 0.0
        self._append_row(round(min(last + self.step, self.max_at), 4), "#FFFFFF")
        self.canvas.yview_moveto(1.0)

    def _refresh_footer(self) -> None:
        self.add_button.configure(
            state="normal" if len(self.rows) < self.limit else "disabled"
        )
        self.count_label.configure(text=f"{len(self.rows)} / {self.limit} 段")

    def get_bands(self) -> list[dict]:
        """返回原始输入，at 解析失败时为 None，由保存时统一校验。"""
        out = []
        for row in self.rows:
            raw = row["at"].get().strip()
            try:
                at = float(raw)
            except ValueError:
                at = None
            out.append({"at": at, "color": row["color"]})
        return out


class SettingsWindow:

    def __init__(self, config: Config) -> None:
        self.config = config
        self._result: bool = False
        self.integer_color = "#FFFFFF"
        self._bands = {"fraction": [], "hundreds": []}

    def show(self, on_saved=None) -> bool:
        self._result = False
        self._on_saved = on_saved

        self.root = tk.Tk()
        self.root.title("VisualizeBalance 设置")
        self.root.geometry("660x600")
        self.root.minsize(620, 560)
        self.root.attributes("-topmost", True)

        self._build_ui()
        self._load_values()

        self.root.mainloop()
        return self._result

    # ------------------------------------------------------------------
    # 界面
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        pad = {"padx": 10, "pady": 5}

        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        notebook = ttk.Notebook(self.root)
        notebook.grid(row=0, column=0, sticky="nsew", padx=10, pady=(10, 4))

        basic = ttk.Frame(notebook, padding=10)
        badge = ttk.Frame(notebook, padding=10)
        notice = ttk.Frame(notebook, padding=10)
        notebook.add(basic, text=" 基本 ")
        notebook.add(badge, text=" 托盘徽标 ")
        notebook.add(notice, text=" 通知 ")

        # ---------------- 基本 ----------------
        ttk.Label(basic, text="API 提供商").grid(row=0, column=0, sticky="w", **pad)
        self.provider_var = tk.StringVar()
        ttk.Combobox(
            basic, textvariable=self.provider_var,
            values=_PROVIDER_OPTIONS, state="readonly", width=28,
        ).grid(row=0, column=1, sticky="w", **pad)

        ttk.Label(basic, text="API Key").grid(row=1, column=0, sticky="w", **pad)
        self.key_var = tk.StringVar()
        ttk.Entry(basic, textvariable=self.key_var, width=36, show="*").grid(
            row=1, column=1, sticky="w", **pad
        )

        ttk.Label(basic, text="告警阈值 (元)").grid(row=2, column=0, sticky="w", **pad)
        self.threshold_var = tk.StringVar()
        ttk.Entry(basic, textvariable=self.threshold_var, width=10).grid(
            row=2, column=1, sticky="w", **pad
        )

        ttk.Label(basic, text="轮询间隔 (秒)").grid(row=3, column=0, sticky="w", **pad)
        self.poll_var = tk.StringVar()
        ttk.Entry(basic, textvariable=self.poll_var, width=10).grid(
            row=3, column=1, sticky="w", **pad
        )

        self.sound_var = tk.BooleanVar()
        ttk.Checkbutton(basic, text="启用提示音", variable=self.sound_var).grid(
            row=4, column=0, columnspan=2, sticky="w", **pad
        )

        self.autostart_var = tk.BooleanVar()
        ttk.Checkbutton(basic, text="开机自动启动", variable=self.autostart_var).grid(
            row=5, column=0, columnspan=2, sticky="w", **pad
        )

        # ---------------- 托盘徽标 ----------------
        badge.columnconfigure(0, weight=1)

        ttk.Label(badge, text="显示方式").grid(row=0, column=0, sticky="w", **pad)
        self.mode_var = tk.StringVar()
        ttk.Combobox(
            badge, textvariable=self.mode_var,
            values=list(_MODE_LABELS.values()), state="readonly", width=16,
        ).grid(row=0, column=1, sticky="w", **pad)

        ttk.Label(badge, text="水位格单位（元，正整数）").grid(row=1, column=0, sticky="w", **pad)
        self.unit_var = tk.StringVar()
        ttk.Entry(badge, textvariable=self.unit_var, width=10).grid(
            row=1, column=1, sticky="w", **pad
        )

        ttk.Label(badge, text="整数余额颜色").grid(row=2, column=0, sticky="w", **pad)
        self.integer_swatch = tk.Button(
            badge, text="    ", width=4, bg=self.integer_color,
            relief="raised", command=self._pick_integer_color,
        )
        self.integer_swatch.grid(row=2, column=1, sticky="w", **pad)

        ttk.Label(badge, text="颜色分段").grid(row=3, column=0, sticky="nw", **pad)
        domain = ttk.Frame(badge)
        domain.grid(row=3, column=1, sticky="w", **pad)
        self.domain_var = tk.StringVar(value="fraction")
        ttk.Radiobutton(
            domain, text="十位级（按零头 0~1，最多 10 段）",
            variable=self.domain_var, value="fraction",
            command=self._switch_domain,
        ).pack(anchor="w")
        ttk.Radiobutton(
            domain, text="百元级（按绝对金额，最多 20 段）",
            variable=self.domain_var, value="hundreds",
            command=self._switch_domain,
        ).pack(anchor="w")

        self.band_editor = BandEditor(badge)
        self.band_editor.grid(row=4, column=0, columnspan=2, sticky="nsew", pady=(6, 0))

        ttk.Label(
            badge,
            text=(
                "每一段从「大于等于」的值开始，直到下一段的起始值；颜色点击色块从色盘选择。\n"
                "余额正好是整数时使用上面的整数颜色。"
            ),
            foreground="gray",
        ).grid(row=5, column=0, columnspan=2, sticky="w", padx=10, pady=(8, 0))

        # ---------------- 通知 ----------------
        self.flash_var = tk.BooleanVar()
        ttk.Checkbutton(
            notice, text="任务完成时闪烁托盘图标", variable=self.flash_var
        ).grid(row=0, column=0, columnspan=2, sticky="w", **pad)

        ttk.Label(notice, text="闪烁时长（秒）").grid(row=1, column=0, sticky="w", **pad)
        self.flash_secs_var = tk.StringVar()
        ttk.Entry(notice, textvariable=self.flash_secs_var, width=10).grid(
            row=1, column=1, sticky="w", **pad
        )

        self.toast_var = tk.BooleanVar()
        ttk.Checkbutton(
            notice, text="任务完成时弹出提示窗（Toast）", variable=self.toast_var
        ).grid(row=2, column=0, columnspan=2, sticky="w", **pad)

        ttk.Label(
            notice,
            text="提示音在「基本」页单独开关；闪烁时长填 0 表示不闪。",
            foreground="gray",
        ).grid(row=3, column=0, columnspan=2, sticky="w", padx=10, pady=(8, 0))

        # ---------------- 按钮 ----------------
        buttons = ttk.Frame(self.root)
        buttons.grid(row=1, column=0, pady=8)
        ttk.Button(buttons, text="保存", command=self._on_save, width=10).pack(side="left", padx=8)
        ttk.Button(buttons, text="取消", command=self._on_cancel, width=10).pack(side="left", padx=8)

        ttk.Label(
            self.root,
            text="配置保存到 %APPDATA%/VisualizeBalance/config.json",
            foreground="gray",
        ).grid(row=2, column=0, sticky="w", padx=20, pady=(0, 8))

    # ------------------------------------------------------------------
    # 读取 / 保存
    # ------------------------------------------------------------------

    def _load_values(self) -> None:
        cfg = self.config
        self.provider_var.set(cfg.get("provider", "deepseek"))
        self.key_var.set(cfg.get("api_key", ""))
        self.threshold_var.set(str(cfg.get("alert_threshold", 1.0)))
        self.poll_var.set(str(cfg.get("poll_interval", 120)))
        self.sound_var.set(cfg.get("sound_enabled", True))
        self.autostart_var.set(cfg.get("auto_start", False))

        self.mode_var.set(
            _MODE_LABELS.get(cfg.get("badge_display_mode", "both"), "数字 + 水位")
        )
        self.unit_var.set(str(cfg.get("badge_water_unit", 1)))

        self.integer_color = str(cfg.get("badge_integer_color", "#FFFFFF")).upper()
        self.integer_swatch.configure(bg=self.integer_color)

        self._bands = {
            "fraction": [dict(b) for b in cfg.get("badge_bands", [])],
            "hundreds": [dict(b) for b in cfg.get("badge_hundreds_bands", [])],
        }
        self.domain_var.set("fraction")
        self._band_editor_limit()
        self.band_editor.set_bands(self._bands["fraction"])

        self.flash_var.set(bool(cfg.get("flash_enabled", True)))
        self.flash_secs_var.set(str(round(int(cfg.get("flash_timeout", 30000)) / 1000)))
        self.toast_var.set(bool(cfg.get("task_toast_enabled", True)))

    def _band_editor_limit(self) -> None:
        if self.domain_var.get() == "hundreds":
            # 百元级最细粒度 5 元
            self.band_editor.set_limit(_MAX_HUNDREDS_BANDS, step=5.0, max_at=1e9)
        else:
            # 十位级按零头 0~1，最多 10 段
            self.band_editor.set_limit(_MAX_FRACTION_BANDS, step=0.1, max_at=1.0)

    def _switch_domain(self) -> None:
        self._store_bands()
        self._band_editor_limit()
        self.band_editor.set_bands(self._bands[self.domain_var.get()])

    def _store_bands(self) -> None:
        self._bands[self.domain_var.get()] = self.band_editor.get_bands()

    def _pick_integer_color(self) -> None:
        _rgb, chosen = colorchooser.askcolor(
            color=self.integer_color, parent=self.root, title="选择整数余额颜色"
        )
        if chosen:
            self.integer_color = chosen.upper()
            self.integer_swatch.configure(bg=self.integer_color)

    @staticmethod
    def _validate_bands(items, low: float, high: float, limit: int, label: str) -> list:
        if not items:
            raise ValueError(f"{label}至少要有一段")
        if len(items) > limit:
            raise ValueError(f"{label}最多 {limit} 段")

        out = []
        for item in items:
            at = item.get("at")
            if at is None:
                raise ValueError(f"{label}的阈值必须全部填写为数字")
            if not (low <= at <= high):
                raise ValueError(f"{label}的阈值需在 {low:g} 到 {high:g} 之间")
            color = str(item.get("color", ""))
            if not _HEX_COLOR_RE.match(color):
                raise ValueError(f"{label}的颜色值非法：{color}")
            out.append({"at": round(float(at), 4), "color": color.upper()})

        out.sort(key=lambda b: b["at"])
        if out[0]["at"] > low:
            out.insert(0, {"at": low, "color": out[0]["color"]})
        if len(out) > limit:
            raise ValueError(f"{label}最多 {limit} 段")
        return out

    def _on_save(self) -> None:
        key = self.key_var.get().strip()
        if not key:
            messagebox.showwarning("提示", "请填写 API Key", parent=self.root)
            return

        try:
            threshold = float(self.threshold_var.get())
        except ValueError:
            messagebox.showwarning("提示", "告警阈值必须是数字", parent=self.root)
            return

        try:
            poll = int(self.poll_var.get())
            if poll < 10:
                messagebox.showwarning("提示", "轮询间隔不能小于 10 秒", parent=self.root)
                return
        except ValueError:
            messagebox.showwarning("提示", "轮询间隔必须是整数", parent=self.root)
            return

        try:
            water_unit = int(self.unit_var.get())
        except ValueError:
            messagebox.showwarning("提示", "水位格单位必须是正整数（单位：元）", parent=self.root)
            return
        if water_unit < 1:
            messagebox.showwarning("提示", "水位格单位必须是正整数（单位：元）", parent=self.root)
            return

        try:
            flash_secs = int(self.flash_secs_var.get())
        except ValueError:
            messagebox.showwarning("提示", "闪烁时长必须是整数秒", parent=self.root)
            return
        if not (0 <= flash_secs <= 3600):
            messagebox.showwarning("提示", "闪烁时长需在 0~3600 秒之间", parent=self.root)
            return

        self._store_bands()
        try:
            bands = self._validate_bands(
                self._bands["fraction"], 0.0, 1.0, _MAX_FRACTION_BANDS, "十位级"
            )
            hundreds_bands = self._validate_bands(
                self._bands["hundreds"], 0.0, 1e9, _MAX_HUNDREDS_BANDS, "百元级"
            )
        except ValueError as exc:
            messagebox.showwarning("提示", str(exc), parent=self.root)
            return

        cfg = self.config
        cfg.set("provider", self.provider_var.get())
        cfg.set("api_key", key)
        cfg.set("alert_threshold", threshold)
        cfg.set("poll_interval", poll)
        cfg.set("sound_enabled", self.sound_var.get())
        cfg.set("auto_start", self.autostart_var.get())
        cfg.set("badge_display_mode", _MODE_KEYS.get(self.mode_var.get(), "both"))
        cfg.set("badge_water_unit", water_unit)
        cfg.set("badge_integer_color", self.integer_color)
        cfg.set("badge_bands", bands)
        cfg.set("badge_hundreds_bands", hundreds_bands)
        cfg.set("flash_enabled", self.flash_var.get())
        cfg.set("flash_timeout", flash_secs * 1000)
        cfg.set("task_toast_enabled", self.toast_var.get())
        cfg.save()

        self._set_autostart(self.autostart_var.get())

        self._result = True
        messagebox.showinfo("成功", "配置已保存，正在生效…", parent=self.root)
        self.root.destroy()

        if self._on_saved:
            self._on_saved()

    def _on_cancel(self) -> None:
        self.root.destroy()

    _REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
    _APP_NAME = "VisualizeBalance"

    @classmethod
    def _set_autostart(cls, enabled: bool) -> None:
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, cls._REG_PATH, 0, winreg.KEY_SET_VALUE
            )
            if enabled:
                winreg.SetValueEx(
                    key, cls._APP_NAME, 0, winreg.REG_SZ, f'"{_get_exe_path()}"'
                )
            else:
                try:
                    winreg.DeleteValue(key, cls._APP_NAME)
                except FileNotFoundError:
                    pass
            winreg.CloseKey(key)
        except OSError as exc:
            log.warning("设置开机自启失败: %s", exc)
