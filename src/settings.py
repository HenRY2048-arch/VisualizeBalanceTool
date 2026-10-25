"""设置窗口 — tkinter 实现，用于可视化配置 API Key 等参数"""

import logging
import re
import sys
import tkinter as tk
import winreg
from datetime import date
from tkinter import colorchooser, messagebox, ttk
from pathlib import Path

from .config import Config
from .icons import create_balance_badge_icon, hex_to_rgb

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


def _hex_rgb(value: str) -> tuple:
    if not _HEX_COLOR_RE.match(value or ""):
        return (255, 255, 255)
    raw = value.lstrip("#")
    return tuple(int(raw[i:i + 2], 16) for i in (0, 2, 4))


def _text_on(value: str) -> str:
    r, g, b = _hex_rgb(value)
    return "#000000" if (r * 299 + g * 587 + b * 114) / 1000 > 140 else "#FFFFFF"


class SpectrumEditor(ttk.Frame):
    """
    纵向光谱阈值控制器。

    - 下方是低值，上方是高值。
    - 每一段用该段颜色填充，段与段之间的白色分界线可以上下拖动改变阈值。
    - 点击某一段可以打开色盘修改该段颜色。
    """

    WIDTH = 170
    HEIGHT = 250
    PAD = 12

    def __init__(self, master, on_change=None) -> None:
        super().__init__(master)
        self.on_change = on_change
        self.bands: list[dict] = []
        self.low = 0.0
        self.high = 1.0
        self.min_gap = 0.01
        self.limit = _MAX_FRACTION_BANDS
        self._drag: int | None = None

        self.canvas = tk.Canvas(
            self, width=self.WIDTH, height=self.HEIGHT,
            highlightthickness=1, highlightbackground="#B0B0B0", bg="#FFFFFF",
        )
        self.canvas.grid(row=0, column=0, sticky="nw")

        self.legend = tk.Text(
            self, width=26, height=15, bd=0, highlightthickness=1,
            highlightbackground="#B0B0B0", font=("Consolas", 9),
        )
        self.legend.grid(row=0, column=1, sticky="nsew", padx=(8, 0))

        footer = ttk.Frame(self)
        footer.grid(row=1, column=0, columnspan=2, sticky="w", pady=(6, 0))
        self.add_button = ttk.Button(footer, text="添加一段", command=self.add_band)
        self.add_button.pack(side="left")
        self.count_label = ttk.Label(footer, text="", foreground="gray")
        self.count_label.pack(side="left", padx=(10, 0))

        self.columnconfigure(1, weight=1)
        self.canvas.bind("<Button-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_motion)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)

    # ------------------------------------------------------------------
    # 坐标换算
    # ------------------------------------------------------------------

    def _y(self, value: float) -> float:
        span = self.HEIGHT - 2 * self.PAD
        total = self.high - self.low
        frac = 0.0 if total <= 0 else (value - self.low) / total
        frac = min(max(frac, 0.0), 1.0)
        return self.HEIGHT - self.PAD - frac * span

    def _value(self, y: float) -> float:
        span = self.HEIGHT - 2 * self.PAD
        frac = (self.HEIGHT - self.PAD - y) / span if span else 0.0
        frac = min(max(frac, 0.0), 1.0)
        return self.low + frac * (self.high - self.low)

    # ------------------------------------------------------------------
    # 数据
    # ------------------------------------------------------------------

    def set_scale(self, low: float, high: float, min_gap: float, limit: int,
                  step: float = 1.0) -> None:
        self.low = low
        self.high = max(high, low + min_gap)
        self.min_gap = min_gap
        self.limit = limit
        self.step = step
        self.max_at = self.high
        self._refresh_footer()
        self.redraw()

    def set_bands(self, bands) -> None:
        self.bands = sorted(
            [dict(b) for b in (bands or [])], key=lambda b: float(b.get("at", 0))
        )
        self.redraw()

    def get_bands(self) -> list[dict]:
        return [dict(b) for b in self.bands]

    def add_band(self) -> None:
        if len(self.bands) >= self.limit or not self.bands:
            return

        edges = [self.low] + [float(b["at"]) for b in self.bands] + [self.high]
        best_gap = 0.0
        best_at = None
        for a, b in zip(edges, edges[1:]):
            gap = b - a
            if gap > best_gap:
                best_gap = gap
                best_at = a + gap / 2
        if best_at is None or best_gap <= self.min_gap * 2:
            return

        self.bands.append({"at": round(best_at, 4), "color": "#808080"})
        self.bands.sort(key=lambda b: float(b["at"]))
        self.redraw()

    # ------------------------------------------------------------------
    # 绘制
    # ------------------------------------------------------------------

    def redraw(self) -> None:
        c = self.canvas
        c.delete("all")

        left = self.PAD + 22
        right = self.WIDTH - self.PAD

        if not self.bands:
            c.create_text(self.WIDTH / 2, self.HEIGHT / 2, text="没有分段", fill="#888888")
            self._refresh_footer()
            return

        for i, band in enumerate(self.bands):
            top_val = (
                float(self.bands[i + 1]["at"])
                if i + 1 < len(self.bands) else self.high
            )
            y_top = self._y(top_val)
            y_bot = self._y(float(band["at"]))
            color = band.get("color", "#FFFFFF")
            c.create_rectangle(left, y_top, right, y_bot, fill=color, outline="")
            if y_bot - y_top > 16:
                c.create_text(
                    (left + right) / 2, (y_top + y_bot) / 2,
                    text=f"{float(band['at']):g} ~ {top_val:g}",
                    fill=_text_on(color), font=("Consolas", 7),
                )

        for i, band in enumerate(self.bands):
            if i == 0:
                continue
            y = self._y(float(band["at"]))
            c.create_line(left - 6, y, right + 6, y, fill="#FFFFFF", width=2)
            c.create_line(left - 6, y, right + 6, y, fill="#000000", width=1, dash=(2, 2))

        c.create_text(left - 10, self._y(self.high), text=f"{self.high:g}",
                      anchor="e", font=("Consolas", 7), fill="#444444")
        c.create_text(left - 10, self._y(self.low), text=f"{self.low:g}",
                      anchor="e", font=("Consolas", 7), fill="#444444")

        c.create_text(self.WIDTH / 2, 6, text="高", fill="#666666",
                      font=("Microsoft YaHei", 7))
        c.create_text(self.WIDTH / 2, self.HEIGHT - 6, text="低", fill="#666666",
                      font=("Microsoft YaHei", 7))

        self._refresh_legend()
        self._refresh_footer()
        if self.on_change is not None:
            self.on_change()

    def _refresh_legend(self) -> None:
        self.legend.configure(state="normal")
        self.legend.delete("1.0", "end")
        for i, band in enumerate(self.bands):
            top_val = (
                float(self.bands[i + 1]["at"])
                if i + 1 < len(self.bands) else self.high
            )
            tag = f"c{i}"
            self.legend.insert("end", "■ ", tag)
            self.legend.insert("end", f"{float(band['at']):g} ~ {top_val:g}\n")
            self.legend.tag_configure(tag, foreground=band.get("color", "#FFFFFF"))
        self.legend.configure(state="disabled")

    def _refresh_footer(self) -> None:
        self.add_button.configure(
            state="normal" if len(self.bands) < self.limit else "disabled"
        )
        self.count_label.configure(text=f"{len(self.bands)} / {self.limit} 段")

    # ------------------------------------------------------------------
    # 交互
    # ------------------------------------------------------------------

    def _on_press(self, event) -> None:
        if not self.bands:
            return

        nearest = None
        for i in range(1, len(self.bands)):
            y = self._y(float(self.bands[i]["at"]))
            distance = abs(event.y - y)
            if distance <= 7 and (nearest is None or distance < nearest[1]):
                nearest = (i, distance)
        if nearest is not None:
            self._drag = nearest[0]
            return

        value = self._value(event.y)
        index = 0
        for i, band in enumerate(self.bands):
            if value + 1e-9 >= float(band["at"]):
                index = i
        self._pick_color(index)

    def _on_motion(self, event) -> None:
        if self._drag is None:
            return

        i = self._drag
        value = self._value(event.y)
        lower = float(self.bands[i - 1]["at"]) + self.min_gap
        if i + 1 < len(self.bands):
            upper = float(self.bands[i + 1]["at"]) - self.min_gap
        else:
            upper = self.high
        value = min(max(value, lower), max(lower, upper))
        self.bands[i]["at"] = int(round(value))
        self.redraw()

    def _on_release(self, _event) -> None:
        self._drag = None

    def _pick_color(self, index: int) -> None:
        current = self.bands[index].get("color", "#FFFFFF")
        _rgb, chosen = colorchooser.askcolor(
            color=current, parent=self, title="选择该分段的数字颜色"
        )
        if chosen:
            self.bands[index]["color"] = chosen.upper()
            self.redraw()


class SettingsWindow:

    def __init__(self, config: Config) -> None:
        self.config = config
        self._result: bool = False
        self._bands = {"fraction": [], "hundreds": []}
        self._current_domain = "fraction"

    def show(self, on_saved=None) -> bool:
        self._result = False
        self._on_saved = on_saved

        self.root = tk.Tk()
        self.root.title("VisualizeBalance 设置")
        self.root.geometry("760x640")
        self.root.minsize(720, 600)
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
        appearance = ttk.Frame(notebook, padding=10)
        notice = ttk.Frame(notebook, padding=10)
        notebook.add(basic, text=" 基本 ")
        notebook.add(badge, text=" 托盘徽标 ")
        notebook.add(appearance, text=" 外观 ")
        notebook.add(notice, text=" 通知 ")

        # ---------------- 基本 ----------------
        ttk.Label(basic, text="API 提供商").grid(row=0, column=0, sticky="w", **pad)
        self.provider_var = tk.StringVar()
        ttk.Combobox(
            basic, textvariable=self.provider_var,
            values=_PROVIDER_OPTIONS, state="readonly", width=24,
        ).grid(row=0, column=1, sticky="w", **pad)

        ttk.Label(basic, text="API Key").grid(row=1, column=0, sticky="w", **pad)
        self.key_var = tk.StringVar()
        ttk.Entry(basic, textvariable=self.key_var, width=42, show="*").grid(
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

        ttk.Label(basic, text="初始余额 (美元)").grid(row=4, column=0, sticky="w", **pad)
        self.initial_var = tk.StringVar()
        ttk.Entry(basic, textvariable=self.initial_var, width=10).grid(
            row=4, column=1, sticky="w", **pad
        )

        ttk.Label(basic, text="统计起始日期").grid(row=5, column=0, sticky="w", **pad)
        self.start_date_var = tk.StringVar()
        ttk.Entry(basic, textvariable=self.start_date_var, width=16).grid(
            row=5, column=1, sticky="w", **pad
        )
        ttk.Button(
            basic, text="设为今天", width=9, command=self._set_start_today
        ).grid(row=5, column=2, sticky="w", padx=(0, 10), pady=5)
        ttk.Label(
            basic,
            text=(
                "仅 OpenAI 花费统计使用；起始日期格式 YYYY-MM-DD，留空表示从最早开始。\n"
                "充值后：把初始余额改成新的总额，再点「设为今天」重置统计起点。"
            ),
            foreground="gray",
        ).grid(row=6, column=0, columnspan=3, sticky="w", padx=10)

        self.sound_var = tk.BooleanVar()
        ttk.Checkbutton(basic, text="启用提示音", variable=self.sound_var).grid(
            row=7, column=0, columnspan=2, sticky="w", **pad
        )

        self.autostart_var = tk.BooleanVar()
        ttk.Checkbutton(basic, text="开机自动启动", variable=self.autostart_var).grid(
            row=8, column=0, columnspan=2, sticky="w", **pad
        )

        # ---------------- 托盘徽标 ----------------
        badge.columnconfigure(0, weight=1)

        ttk.Label(badge, text="显示方式").grid(row=0, column=0, sticky="w", **pad)
        self.mode_var = tk.StringVar()
        ttk.Combobox(
            badge, textvariable=self.mode_var,
            values=list(_MODE_LABELS.values()), state="readonly", width=16,
        ).grid(row=0, column=1, sticky="w", **pad)

        ttk.Label(badge, text="水位格单位（元）").grid(row=1, column=0, sticky="w", **pad)
        self.unit_var = tk.StringVar()
        ttk.Entry(badge, textvariable=self.unit_var, width=10).grid(
            row=1, column=1, sticky="w", **pad
        )
        ttk.Label(
            badge,
            text="例如填 1：每消耗 1 元，水位从满到空一次；填 10：每消耗 10 元循环一次。",
            foreground="gray",
        ).grid(row=2, column=0, columnspan=2, sticky="w", padx=10)

        ttk.Label(badge, text="颜色分段").grid(row=3, column=0, sticky="nw", **pad)
        domain = ttk.Frame(badge)
        domain.grid(row=3, column=1, sticky="w", **pad)
        self.domain_var = tk.StringVar(value="fraction")
        ttk.Radiobutton(
            domain, text="十位级（余额 0~99，最多 10 段）",
            variable=self.domain_var, value="fraction",
            command=self._switch_domain,
        ).pack(anchor="w")
        ttk.Radiobutton(
            domain, text="百元级（余额 ≥100，最多 20 段）",
            variable=self.domain_var, value="hundreds",
            command=self._switch_domain,
        ).pack(anchor="w")
        self.range_label = ttk.Label(domain, text="", foreground="gray")
        self.range_label.pack(anchor="w", pady=(4, 0))

        self.spectrum = SpectrumEditor(badge, on_change=self._update_preview)
        self.spectrum.grid(row=4, column=0, columnspan=2, sticky="nsew", pady=(6, 0))

        ttk.Label(
            badge,
            text=(
                "竖条下方是低值、上方是高值；白色虚线是分段边界，可直接上下拖动。\n"
                "点击某一段可打开色盘修改该段颜色。"
            ),
            foreground="gray",
        ).grid(row=6, column=0, columnspan=2, sticky="w", padx=10, pady=(8, 0))

        # ---------------- 外观 ----------------
        self.water_color = "#00BFFF"
        self.flash_color = "#FF3B30"
        self.water_alpha_var = tk.IntVar(value=72)
        self.text_alpha_var = tk.IntVar(value=255)
        self.flash_width_var = tk.IntVar(value=8)

        ttk.Label(appearance, text="水位颜色").grid(row=0, column=0, sticky="w", **pad)
        self.water_swatch = tk.Button(
            appearance, text="    ", width=4, bg=self.water_color,
            relief="raised", command=self._pick_water_color,
        )
        self.water_swatch.grid(row=0, column=1, sticky="w", **pad)

        ttk.Label(appearance, text="水位透明度").grid(row=1, column=0, sticky="w", **pad)
        ttk.Scale(
            appearance, from_=0, to=255, orient="horizontal",
            variable=self.water_alpha_var, length=200,
        ).grid(row=1, column=1, sticky="w", **pad)

        ttk.Label(appearance, text="数字透明度").grid(row=2, column=0, sticky="w", **pad)
        ttk.Scale(
            appearance, from_=0, to=255, orient="horizontal",
            variable=self.text_alpha_var, length=200,
        ).grid(row=2, column=1, sticky="w", **pad)

        ttk.Label(appearance, text="描边颜色").grid(row=3, column=0, sticky="w", **pad)
        self.flash_swatch = tk.Button(
            appearance, text="    ", width=4, bg=self.flash_color,
            relief="raised", command=self._pick_flash_color,
        )
        self.flash_swatch.grid(row=3, column=1, sticky="w", **pad)

        ttk.Label(appearance, text="描边强度").grid(row=4, column=0, sticky="w", **pad)
        ttk.Scale(
            appearance, from_=1, to=16, orient="horizontal",
            variable=self.flash_width_var, length=200,
        ).grid(row=4, column=1, sticky="w", **pad)

        preview = ttk.Frame(appearance)
        preview.grid(row=5, column=0, columnspan=2, sticky="w", pady=(12, 0))
        ttk.Label(preview, text="正常").pack(side="left")
        self.preview_normal = tk.Label(preview)
        self.preview_normal.pack(side="left", padx=(6, 24))
        ttk.Label(preview, text="闪烁").pack(side="left")
        self.preview_alert = tk.Label(preview)
        self.preview_alert.pack(side="left", padx=(6, 0))

        for var in (self.water_alpha_var, self.text_alpha_var, self.flash_width_var):
            var.trace_add("write", lambda *_: self._update_preview())
        self.mode_var.trace_add("write", lambda *_: self._update_preview())

        ttk.Label(
            appearance,
            text="水位先绘制、数字最后绘制，因此数字始终在颜色背景之上。",
            foreground="gray",
        ).grid(row=6, column=0, columnspan=2, sticky="w", padx=10, pady=(10, 0))

        # ---------------- 通知 ----------------
        self.flash_var = tk.BooleanVar()
        ttk.Checkbutton(
            notice, text="任务完成时闪烁托盘图标（红色描边）", variable=self.flash_var
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

        ttk.Label(notice, text="安静判定（秒）").grid(row=3, column=0, sticky="w", **pad)
        self.quiet_var = tk.StringVar()
        ttk.Entry(notice, textvariable=self.quiet_var, width=10).grid(
            row=3, column=1, sticky="w", **pad
        )
        ttk.Label(
            notice,
            text=(
                "Codex 分阶段输出时，最后一条消息之后需要安静这么久才认为任务完成。\n"
                "调大可减少中间回复误报，但提示会更晚。"
            ),
            foreground="gray",
        ).grid(row=4, column=0, columnspan=2, sticky="w", padx=10, pady=(6, 0))

        ttk.Label(
            notice,
            text="提示音在「基本」页单独开关；闪烁时长填 0 表示不闪。",
            foreground="gray",
        ).grid(row=5, column=0, columnspan=2, sticky="w", padx=10, pady=(8, 0))

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
        self.initial_var.set(str(cfg.get("openai_initial_balance", 0.0)))
        self.start_date_var.set(str(cfg.get("openai_costs_start_date", "")))
        self.sound_var.set(cfg.get("sound_enabled", True))
        self.autostart_var.set(cfg.get("auto_start", False))

        self.mode_var.set(
            _MODE_LABELS.get(cfg.get("badge_display_mode", "both"), "数字 + 水位")
        )
        self.unit_var.set(str(cfg.get("badge_water_unit", 1)))
        self._bands = {
            "fraction": [dict(b) for b in cfg.get("badge_bands", [])],
            "hundreds": [dict(b) for b in cfg.get("badge_hundreds_bands", [])],
        }
        self.domain_var.set("fraction")
        self._current_domain = "fraction"
        self._apply_domain()

        self.flash_var.set(bool(cfg.get("flash_enabled", True)))
        self.flash_secs_var.set(str(round(int(cfg.get("flash_timeout", 30000)) / 1000)))
        self.toast_var.set(bool(cfg.get("task_toast_enabled", True)))
        self.quiet_var.set(str(cfg.get("notify_quiet_seconds", 10)))

        self.water_color = str(cfg.get("badge_water_color", "#00BFFF")).upper()
        self.flash_color = str(cfg.get("badge_flash_color", "#FF3B30")).upper()
        self.water_swatch.configure(bg=self.water_color)
        self.flash_swatch.configure(bg=self.flash_color)
        self.water_alpha_var.set(int(cfg.get("badge_water_alpha", 72)))
        self.text_alpha_var.set(int(cfg.get("badge_text_alpha", 255)))
        self.flash_width_var.set(int(cfg.get("badge_flash_width", 8)))
        self._update_preview()

    def _apply_domain(self) -> None:
        self._current_domain = self.domain_var.get()
        if self.domain_var.get() == "hundreds":
            bands = self._bands["hundreds"]
            high = max(1000.0, max((float(b["at"]) for b in bands), default=0.0) * 1.2)
            self.spectrum.set_scale(0.0, high, 1.0, _MAX_HUNDREDS_BANDS, step=1.0)
            self.range_label.configure(text=f"当前范围：0 ~ {high:.0f}（整数金额）")
        else:
            bands = self._bands["fraction"]
            self.spectrum.set_scale(0.0, 99.0, 1.0, _MAX_FRACTION_BANDS, step=1.0)
            self.range_label.configure(text="当前范围：0 ~ 99（整数金额）")
        self.spectrum.set_bands(bands)

    def _switch_domain(self) -> None:
        self._bands[self._current_domain] = self.spectrum.get_bands()
        self._apply_domain()

    def _set_start_today(self) -> None:
        self.start_date_var.set(date.today().isoformat())

    def _pick_water_color(self) -> None:
        _rgb, chosen = colorchooser.askcolor(
            color=self.water_color, parent=self.root, title="选择水位颜色"
        )
        if chosen:
            self.water_color = chosen.upper()
            self.water_swatch.configure(bg=self.water_color)
            self._update_preview()

    def _pick_flash_color(self) -> None:
        _rgb, chosen = colorchooser.askcolor(
            color=self.flash_color, parent=self.root, title="选择描边颜色"
        )
        if chosen:
            self.flash_color = chosen.upper()
            self.flash_swatch.configure(bg=self.flash_color)
            self._update_preview()

    def _preview_color(self) -> tuple:
        spectrum = getattr(self, "spectrum", None)
        bands = spectrum.get_bands() if spectrum else []
        for band in reversed(bands):
            color = band.get("color")
            if isinstance(color, str) and _HEX_COLOR_RE.match(color):
                return hex_to_rgb(color)
        return (255, 165, 0)

    def _update_preview(self) -> None:
        if not hasattr(self, "preview_normal"):
            return
        try:
            from PIL import ImageTk

            mode = _MODE_KEYS.get(self.mode_var.get(), "both")
            kwargs = {
                "water_color": hex_to_rgb(self.water_color),
                "water_alpha": int(self.water_alpha_var.get()),
                "text_alpha": int(self.text_alpha_var.get()),
                "flash_color": hex_to_rgb(self.flash_color),
                "flash_width": int(self.flash_width_var.get()),
            }
            color = self._preview_color()
            normal = create_balance_badge_icon(
                "20", color, 0.6, mode, size=128, **kwargs
            )
            alert = create_balance_badge_icon(
                "20", color, 0.6, mode, size=128, alert=True, **kwargs
            )
            self._preview_normal_img = ImageTk.PhotoImage(normal)
            self._preview_alert_img = ImageTk.PhotoImage(alert)
            self.preview_normal.configure(image=self._preview_normal_img)
            self.preview_alert.configure(image=self._preview_alert_img)
        except Exception:
            pass

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
                raise ValueError(f"{label}的阈值必须全部是数字")
            if float(at) != int(at):
                raise ValueError(f"{label}的阈值必须是整数")
            at = int(at)
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

        try:
            initial_balance = float(self.initial_var.get())
        except ValueError:
            messagebox.showwarning("提示", "初始余额必须是数字（美元）", parent=self.root)
            return
        start_date = self.start_date_var.get().strip()
        if start_date and not re.match(r"^\d{4}-\d{2}-\d{2}$", start_date):
            messagebox.showwarning("提示", "统计起始日期格式应为 YYYY-MM-DD", parent=self.root)
            return

        try:
            quiet = int(self.quiet_var.get())
        except ValueError:
            messagebox.showwarning("提示", "安静判定必须是整数秒", parent=self.root)
            return
        if not (1 <= quiet <= 300):
            messagebox.showwarning("提示", "安静判定需在 1~300 秒之间", parent=self.root)
            return

        # 保存当前正在编辑的域，再取两套分段
        self._bands[self._current_domain] = self.spectrum.get_bands()
        try:
            bands = self._validate_bands(
                self._bands["fraction"], 0.0, 99.0, _MAX_FRACTION_BANDS, "十位级"
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
        cfg.set("openai_initial_balance", max(initial_balance, 0.0))
        cfg.set("openai_costs_start_date", start_date)
        cfg.set("sound_enabled", self.sound_var.get())
        cfg.set("auto_start", self.autostart_var.get())
        cfg.set("badge_display_mode", _MODE_KEYS.get(self.mode_var.get(), "both"))
        cfg.set("badge_water_unit", water_unit)
        cfg.set("badge_bands", bands)
        cfg.set("badge_hundreds_bands", hundreds_bands)
        cfg.set("flash_enabled", self.flash_var.get())
        cfg.set("flash_timeout", flash_secs * 1000)
        cfg.set("task_toast_enabled", self.toast_var.get())
        cfg.set("notify_quiet_seconds", quiet)
        cfg.set("badge_water_color", self.water_color)
        cfg.set("badge_water_alpha", int(self.water_alpha_var.get()))
        cfg.set("badge_text_alpha", int(self.text_alpha_var.get()))
        cfg.set("badge_flash_color", self.flash_color)
        cfg.set("badge_flash_width", int(self.flash_width_var.get()))
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
