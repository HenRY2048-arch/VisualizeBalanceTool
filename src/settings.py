"""设置窗口 — tkinter 实现，用于可视化配置 API Key 等参数"""

import logging
import os
import winreg
import sys
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path

from .config import Config

log = logging.getLogger(__name__)

_PROVIDER_OPTIONS = ["deepseek", "openai"]


def _get_exe_path() -> str:
    if getattr(sys, "frozen", False):
        return sys.executable
    return str(Path(__file__).resolve().parent.parent / "run.py")


class SettingsWindow:

    def __init__(self, config: Config) -> None:
        self.config = config
        self._result: bool = False

    def show(self, on_saved=None) -> bool:
        self._result = False
        self._on_saved = on_saved

        self.root = tk.Tk()
        self.root.title("VisualizeBalance 设置")
        self.root.geometry("480x440")
        self.root.resizable(False, False)
        self.root.attributes("-topmost", True)

        self._build_ui()
        self._load_values()

        self.root.mainloop()
        return self._result

    def _build_ui(self) -> None:
        pad = {"padx": 12, "pady": 4}

        # --- 提供商 ---
        ttk.Label(self.root, text="API 提供商").grid(row=0, column=0, sticky="w", **pad)
        self.provider_var = tk.StringVar()
        ttk.Combobox(
            self.root, textvariable=self.provider_var,
            values=_PROVIDER_OPTIONS, state="readonly", width=30,
        ).grid(row=0, column=1, sticky="w", **pad)

        # --- API Key（始终遮掩） ---
        ttk.Label(self.root, text="API Key").grid(row=1, column=0, sticky="w", **pad)
        self.key_var = tk.StringVar()
        ttk.Entry(self.root, textvariable=self.key_var, width=38, show="*").grid(
            row=1, column=1, sticky="w", **pad
        )

        # --- 告警阈值 ---
        ttk.Label(self.root, text="告警阈值 (元)").grid(row=2, column=0, sticky="w", **pad)
        self.threshold_var = tk.StringVar()
        ttk.Entry(self.root, textvariable=self.threshold_var, width=10).grid(
            row=2, column=1, sticky="w", **pad
        )

        # --- 轮询间隔 ---
        ttk.Label(self.root, text="轮询间隔 (秒)").grid(row=3, column=0, sticky="w", **pad)
        self.poll_var = tk.StringVar()
        ttk.Entry(self.root, textvariable=self.poll_var, width=10).grid(
            row=3, column=1, sticky="w", **pad
        )

        # --- 提示音 ---
        self.sound_var = tk.BooleanVar()
        ttk.Checkbutton(self.root, text="启用提示音", variable=self.sound_var).grid(
            row=4, column=0, columnspan=2, sticky="w", **pad
        )

        # --- 开机自启 ---
        self.autostart_var = tk.BooleanVar()
        ttk.Checkbutton(self.root, text="开机自动启动", variable=self.autostart_var).grid(
            row=5, column=0, columnspan=2, sticky="w", **pad
        )

        # --- 托盘徽标配色（按余额零头 0.xx 判定） ---
        ttk.Separator(self.root, orient="horizontal").grid(
            row=6, column=0, columnspan=2, sticky="ew", padx=12, pady=(10, 0)
        )
        ttk.Label(self.root, text="托盘徽标配色（按余额零头 0.xx 判定）").grid(
            row=7, column=0, columnspan=2, sticky="w", **pad
        )

        ttk.Label(self.root, text="零头 ≥ 此值显示绿色").grid(row=8, column=0, sticky="w", **pad)
        self.green_var = tk.StringVar()
        ttk.Entry(self.root, textvariable=self.green_var, width=10).grid(
            row=8, column=1, sticky="w", **pad
        )

        ttk.Label(self.root, text="零头 < 此值显示红色").grid(row=9, column=0, sticky="w", **pad)
        self.red_var = tk.StringVar()
        ttk.Entry(self.root, textvariable=self.red_var, width=10).grid(
            row=9, column=1, sticky="w", **pad
        )

        ttk.Label(
            self.root,
            text="介于两者之间为橙色；余额正好是整数时显示白色。阈值取值 0~1。",
            foreground="gray",
        ).grid(row=10, column=0, columnspan=2, sticky="w", padx=12)

        # --- 按钮 ---
        btn_frame = ttk.Frame(self.root)
        btn_frame.grid(row=11, column=0, columnspan=2, pady=16)
        ttk.Button(btn_frame, text="保存", command=self._on_save, width=10).pack(side="left", padx=8)
        ttk.Button(btn_frame, text="取消", command=self._on_cancel, width=10).pack(side="left", padx=8)

        # --- 提示 ---
        ttk.Label(
            self.root,
            text="配置保存到 %APPDATA%/VisualizeBalance/config.json",
            foreground="gray",
        ).grid(row=12, column=0, columnspan=2, sticky="w", padx=12)

    def _load_values(self) -> None:
        cfg = self.config
        self.provider_var.set(cfg.get("provider", "deepseek"))
        self.key_var.set(cfg.get("api_key", ""))
        self.threshold_var.set(str(cfg.get("alert_threshold", 1.0)))
        self.poll_var.set(str(cfg.get("poll_interval", 120)))
        self.sound_var.set(cfg.get("sound_enabled", True))
        self.autostart_var.set(cfg.get("auto_start", False))
        self.green_var.set(str(cfg.get("badge_green_at", 0.50)))
        self.red_var.set(str(cfg.get("badge_red_below", 0.25)))

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
            green_at = float(self.green_var.get())
            red_below = float(self.red_var.get())
        except ValueError:
            messagebox.showwarning("提示", "配色阈值必须是数字", parent=self.root)
            return
        if not (0.0 <= red_below < green_at <= 1.0):
            messagebox.showwarning(
                "提示",
                "配色阈值需要满足：0 ≤ 红色阈值 < 绿色阈值 ≤ 1",
                parent=self.root,
            )
            return

        cfg = self.config
        cfg.set("provider", self.provider_var.get())
        cfg.set("api_key", key)
        cfg.set("alert_threshold", threshold)
        cfg.set("poll_interval", poll)
        cfg.set("sound_enabled", self.sound_var.get())
        cfg.set("auto_start", self.autostart_var.get())
        cfg.set("badge_green_at", green_at)
        cfg.set("badge_red_below", red_below)
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
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, cls._REG_PATH, 0, winreg.KEY_SET_VALUE)
            if enabled:
                winreg.SetValueEx(key, cls._APP_NAME, 0, winreg.REG_SZ, f'"{_get_exe_path()}"')
            else:
                try:
                    winreg.DeleteValue(key, cls._APP_NAME)
                except FileNotFoundError:
                    pass
            winreg.CloseKey(key)
        except OSError as exc:
            log.warning("设置开机自启失败: %s", exc)
