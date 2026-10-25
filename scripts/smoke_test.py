#!/usr/bin/env python3
"""
VisualizeBalance 冒烟测试

覆盖范围：
  1) 托盘余额徽标的配色规则（balance_badge_spec）
  2) 徽标图标能真实渲染（装了 Pillow 时还会校验像素颜色）
  3) 信号文件 -> 通知 + 图标闪烁 全链路（App._tick）
  4) WSL hook 安装脚本：登录 shell 判定、陈旧 hook 清理、bash 守卫
     能真正生成信号文件（需要 bash）

用法：
    python scripts/smoke_test.py

在 Windows（依赖齐全）上会走真实 PIL/pystray；在纯 Linux/WSL 上会自动给缺失
的 Windows-only 依赖打桩，因此不装依赖也能验证核心逻辑。
"""

from __future__ import annotations

import importlib
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

_RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    _RESULTS.append((name, bool(ok), detail))
    flag = "PASS" if ok else "FAIL"
    print(f"  [{flag}] {name}" + (f"  — {detail}" if detail else ""))
    return bool(ok)


def section(title: str) -> None:
    print(f"\n=== {title} ===")


# ---------------------------------------------------------------------------
# 依赖打桩（只补缺失的）
# ---------------------------------------------------------------------------

def _importable(name: str) -> bool:
    try:
        importlib.import_module(name)
        return True
    except Exception:
        return False


REAL_PIL = _importable("PIL.Image")


def _install_stubs() -> None:
    """给缺失的 Windows-only / GUI 依赖打桩，让核心逻辑能在 Linux 上跑。"""
    if not REAL_PIL:
        class _FakeImage:
            def __init__(self, size=(64, 64), mode="RGBA", color=(0, 0, 0, 0)):
                self.size = size
                self.mode = mode

            def convert(self, *a, **k):
                return self

            def resize(self, *a, **k):
                return self

            def putalpha(self, *a, **k):
                return None

            def point(self, *a, **k):
                return self

            def alpha_composite(self, *a, **k):
                return None

        class _FakeDraw:
            def rounded_rectangle(self, *a, **k):
                return None

            def rectangle(self, *a, **k):
                return None

            def textbbox(self, xy, text, font=None, **k):
                return (0, 0, max(1, len(str(text))) * 6, 8)

            def text(self, *a, **k):
                return None

        img_mod = types.ModuleType("PIL.Image")
        img_mod.Image = _FakeImage
        img_mod.new = lambda *a, **k: _FakeImage()
        img_mod.open = lambda *a, **k: _FakeImage()
        img_mod.Resampling = types.SimpleNamespace(LANCZOS=1)

        draw_mod = types.ModuleType("PIL.ImageDraw")
        draw_mod.Draw = lambda *a, **k: _FakeDraw()

        font_mod = types.ModuleType("PIL.ImageFont")
        font_mod.truetype = lambda *a, **k: None
        font_mod.load_default = lambda: None

        pil_mod = types.ModuleType("PIL")
        pil_mod.Image = img_mod
        pil_mod.ImageDraw = draw_mod
        pil_mod.ImageFont = font_mod

        sys.modules.update({
            "PIL": pil_mod,
            "PIL.Image": img_mod,
            "PIL.ImageDraw": draw_mod,
            "PIL.ImageFont": font_mod,
        })

    if not _importable("pystray"):
        mod = types.ModuleType("pystray")
        mod.Icon = type("Icon", (), {})
        mod.Menu = lambda *a, **k: None
        mod.MenuItem = lambda *a, **k: None
        sys.modules["pystray"] = mod

    if not _importable("requests"):
        class _RequestException(Exception):
            pass

        mod = types.ModuleType("requests")
        mod.RequestException = _RequestException

        def _no_network(*a, **k):
            raise _RequestException("network disabled in smoke test")

        mod.get = _no_network
        sys.modules["requests"] = mod

    if not _importable("winreg"):
        sys.modules["winreg"] = types.ModuleType("winreg")

    if not _importable("tkinter"):
        tk = types.ModuleType("tkinter")
        ttk = types.ModuleType("tkinter.ttk")
        messagebox = types.ModuleType("tkinter.messagebox")
        colorchooser = types.ModuleType("tkinter.colorchooser")
        colorchooser.askcolor = lambda *a, **k: ((255, 255, 255), "#ffffff")

        class _FakeWidget:
            def __init__(self, *a, **k):
                pass

            def pack(self, *a, **k):
                pass

            def grid(self, *a, **k):
                pass

            def configure(self, *a, **k):
                pass

            def destroy(self, *a, **k):
                pass

        for _name in ("Frame", "Label", "Button", "Entry", "Combobox",
                      "Checkbutton", "Radiobutton", "Scrollbar", "Notebook",
                      "Separator", "Treeview", "LabelFrame"):
            setattr(ttk, _name, _FakeWidget)
        for _name in ("Canvas", "Button", "StringVar", "BooleanVar", "Tk"):
            setattr(tk, _name, _FakeWidget)

        tk.ttk = ttk
        tk.messagebox = messagebox
        tk.colorchooser = colorchooser
        sys.modules.update({
            "tkinter": tk,
            "tkinter.ttk": ttk,
            "tkinter.messagebox": messagebox,
            "tkinter.colorchooser": colorchooser,
        })


# ---------------------------------------------------------------------------
# 测试 1：配色规则
# ---------------------------------------------------------------------------

def test_badge_spec() -> None:
    from src.icons import (
        BADGE_BANDS_DEFAULT,
        BADGE_DISPLAY_MODE_DEFAULT,
        BADGE_HUNDREDS_BANDS_DEFAULT,
        BADGE_INTEGER_COLOR_DEFAULT,
        BADGE_WATER_UNIT_DEFAULT,
        balance_badge_spec,
        hex_to_rgb,
    )

    section("Test 1: 余额徽标（文字 / 颜色 / 水位）")

    RED = (255, 0, 0)
    ORANGE = (255, 165, 0)
    GREEN = (124, 252, 0)
    WHITE = (255, 255, 255)

    # 默认色带：十位级 0/10/30（整数金额），百元级 0/320/360
    cases = [
        (20.00, "20", ORANGE, 1.00, "20 -> 10~30 段，橙，满水"),
        (0.00, "0", RED, 1.00, "0 -> 红"),
        (9.80, "9", RED, 0.80, "9.80 -> 红，格内 80%"),
        (10.00, "10", ORANGE, 1.00, "10 -> 橙，格线满"),
        (10.20, "10", ORANGE, 0.20, "10.20 -> 10-11 格内 20%"),
        (20.08, "20", ORANGE, 0.08, "20.08 -> 橙"),
        (29.99, "29", ORANGE, 0.99, "29.99 -> 橙"),
        (30.00, "30", GREEN, 1.00, "30 -> 绿"),
        (99.99, "99", GREEN, 0.99, "99.99 -> 绿"),
        (8.96, "8", RED, 0.96, "8.96 -> 红"),
        (None, "--", WHITE, 0.00, "无余额 -> --"),
        (100.00, "1H", RED, 1.00, "100 -> 1H，<320 红"),
        (319.99, "3H", RED, 0.99, "319.99 -> 红"),
        (320.00, "3H", ORANGE, 1.00, "320（红阈值边界）-> 橙"),
        (359.99, "3H", ORANGE, 0.99, "359.99 -> 橙"),
        (360.00, "3H", GREEN, 1.00, "360（绿阈值边界）-> 绿"),
        (379.00, "3H", GREEN, 1.00, "379 -> 3H，满水"),
        (999.00, "9H", GREEN, 1.00, "999 -> 9H"),
        (1234.00, "9H", GREEN, 1.00, "超过 999 封顶 9H"),
    ]
    for value, text, color, level, label in cases:
        got_text, got_color, got_level = balance_badge_spec(value)
        ok = (
            got_text == text
            and got_color == color
            and abs(got_level - level) < 0.001
        )
        check(
            f"{label}（{value}）",
            ok,
            f"期望 ({text}, {color}, {level}) 实际 ({got_text}, {got_color}, {got_level})",
        )

    # 自定义水位格单位
    unit_cases = [
        (379.00, 10, 0.90, "单位 10：379 -> 格内 90%"),
        (375.50, 10, 0.55, "单位 10：375.50 -> 格内 55%"),
        (370.00, 10, 1.00, "单位 10：370 -> 格线，满"),
        (379.00, 100, 0.79, "单位 100：379 -> 格内 79%"),
        (350.00, 100, 0.50, "单位 100：350 -> 格内 50%"),
        (300.00, 100, 1.00, "单位 100：300 -> 格线，满"),
        (12.50, 5, 0.50, "单位 5：12.50 -> 格内 50%"),
    ]
    for value, unit, level, label in unit_cases:
        _, _, got_level = balance_badge_spec(value, water_unit=unit)
        check(label, abs(got_level - level) < 0.001, f"期望 {level} 实际 {got_level}")

    # 十位级自定义 5 段（整数金额）
    custom_bands = [
        {"at": 0, "color": "#FF0000"},
        {"at": 10, "color": "#FF8000"},
        {"at": 20, "color": "#FFFF00"},
        {"at": 30, "color": "#00FF00"},
        {"at": 40, "color": "#00FFFF"},
    ]
    for value, color, label in [
        (5.00, "#FF0000", "十位级 5 段：5 -> 第 1 段"),
        (15.00, "#FF8000", "十位级 5 段：15 -> 第 2 段"),
        (25.00, "#FFFF00", "十位级 5 段：25 -> 第 3 段"),
        (35.00, "#00FF00", "十位级 5 段：35 -> 第 4 段"),
        (45.00, "#00FFFF", "十位级 5 段：45 -> 第 5 段"),
    ]:
        _, got_color, _ = balance_badge_spec(value, bands=custom_bands)
        check(label, got_color == hex_to_rgb(color), f"期望 {color} 实际 {got_color}")

    # 自定义个位数阈值：3 元时设 2 为分界
    single_bands = [
        {"at": 0, "color": "#00FF00"},
        {"at": 2, "color": "#FF0000"},
    ]
    for value, color, label in [
        (1.50, "#00FF00", "个位数：1.50 < 2 -> 绿"),
        (3.00, "#FF0000", "个位数：3.00 >= 2 -> 红"),
    ]:
        _, got_color, _ = balance_badge_spec(value, bands=single_bands)
        check(label, got_color == hex_to_rgb(color), f"期望 {color} 实际 {got_color}")

    # 百元级自定义 4 段
    hundred_bands = [
        {"at": 0, "color": "#FF0000"},
        {"at": 340, "color": "#FFA500"},
        {"at": 360, "color": "#FFFF00"},
        {"at": 380, "color": "#7CFC00"},
    ]
    for value, color, label in [
        (339.99, "#FF0000", "百元级 4 段：339.99 -> 第 1 段"),
        (350.00, "#FFA500", "百元级 4 段：350 -> 第 2 段"),
        (370.00, "#FFFF00", "百元级 4 段：370 -> 第 3 段"),
        (380.00, "#7CFC00", "百元级 4 段：380 -> 第 4 段"),
    ]:
        _, got_color, _ = balance_badge_spec(value, hundreds_bands=hundred_bands)
        check(label, got_color == hex_to_rgb(color), f"期望 {color} 实际 {got_color}")

    # 配置默认值必须与 icons 里的默认值一致
    from src import config as config_mod

    cfg = config_mod.Config()
    check(
        "config 默认值与 icons 默认值一致",
        cfg.get("badge_bands") == BADGE_BANDS_DEFAULT
        and cfg.get("badge_hundreds_bands") == BADGE_HUNDREDS_BANDS_DEFAULT
        and cfg.get("badge_integer_color") == BADGE_INTEGER_COLOR_DEFAULT
        and cfg.get("badge_water_unit") == BADGE_WATER_UNIT_DEFAULT
        and cfg.get("badge_display_mode") == BADGE_DISPLAY_MODE_DEFAULT,
        f"mode={cfg.get('badge_display_mode')} unit={cfg.get('badge_water_unit')}",
    )

    # 手工写坏 config.json 时，兜底必须回到默认值
    config_mod.CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    config_mod.CONFIG_PATH.write_text(
        '{"badge_bands": [{"at": 0, "color": "red"}],'
        ' "badge_hundreds_bands": "oops",'
        ' "badge_integer_color": "white",'
        ' "badge_display_mode": "bogus", "badge_water_unit": 0}',
        encoding="utf-8",
    )
    broken = config_mod.Config()
    check(
        "非法配置被兜底为默认值",
        broken.get("badge_bands") == BADGE_BANDS_DEFAULT
        and broken.get("badge_hundreds_bands") == BADGE_HUNDREDS_BANDS_DEFAULT
        and broken.get("badge_integer_color") == BADGE_INTEGER_COLOR_DEFAULT
        and broken.get("badge_display_mode") == BADGE_DISPLAY_MODE_DEFAULT
        and broken.get("badge_water_unit") == BADGE_WATER_UNIT_DEFAULT,
        "色带、整数颜色、模式、单位都应回退默认",
    )

    # 段数上限：十位级 10 段，百元级 20 段，超出部分被截断
    many = [{"at": i, "color": "#123456"} for i in range(11)]
    many_h = [{"at": i * 5, "color": "#123456"} for i in range(25)]
    config_mod.CONFIG_PATH.write_text(
        '{"badge_bands": %s, "badge_hundreds_bands": %s}'
        % (config_mod.json.dumps(many), config_mod.json.dumps(many_h)),
        encoding="utf-8",
    )
    capped = config_mod.Config()
    check("十位级最多 10 段", len(capped.get("badge_bands")) == 10,
          str(len(capped.get("badge_bands"))))
    check("百元级最多 20 段", len(capped.get("badge_hundreds_bands")) == 20,
          str(len(capped.get("badge_hundreds_bands"))))

    # 旧版百元级阈值键迁移；旧版十位级零头阈值与新整数模型不兼容，回退默认
    config_mod.CONFIG_PATH.write_text(
        '{"badge_red_below": 0.3, "badge_green_at": 0.7,'
        ' "badge_hundreds_red_below": 300, "badge_hundreds_green_at": 400}',
        encoding="utf-8",
    )
    migrated = config_mod.Config()
    check(
        "旧版百元级阈值自动迁移，十位级使用新默认",
        migrated.get("badge_bands") == BADGE_BANDS_DEFAULT
        and [b["at"] for b in migrated.get("badge_hundreds_bands")] == [0, 300, 400],
        str(migrated.get("badge_hundreds_bands")),
    )

    config_mod.CONFIG_PATH.unlink()


# ---------------------------------------------------------------------------
# 测试 2：徽标渲染
# ---------------------------------------------------------------------------

def test_badge_render() -> None:
    from src.icons import BADGE_RED, create_balance_badge_icon

    section("Test 2: 徽标图标渲染")
    img = create_balance_badge_icon("20", BADGE_RED, 0.0)
    check("能创建徽标图片", img is not None)

    if not REAL_PIL:
        print("  [SKIP] 未安装 Pillow，跳过像素校验（已用打桩验证调用链）")
        return

    rgba = img.convert("RGBA")
    # 用 tobytes() 而不是已弃用的 getdata()（Pillow 14 会移除）
    raw = rgba.tobytes()

    def _has(pred) -> bool:
        return any(pred(raw[i], raw[i + 1], raw[i + 2], raw[i + 3]) for i in range(0, len(raw), 4))

    has_black = _has(lambda r, g, b, a: a > 200 and r < 40 and g < 40 and b < 40)
    has_red = _has(lambda r, g, b, a: a > 100 and r > 150 and g < 90 and b < 90)
    corner_alpha = raw[3]
    check("外框四角透明（矩形框留边）", corner_alpha == 0, f"corner_alpha={corner_alpha}")
    check("存在黑色底", has_black)
    check("数字为红色", has_red)
    check("画布尺寸与其它图标一致", rgba.size == (64, 64), str(rgba.size))

    full = create_balance_badge_icon("20", BADGE_RED, 1.0).convert("RGBA")
    half = create_balance_badge_icon("20", BADGE_RED, 0.5).convert("RGBA")
    empty = create_balance_badge_icon("20", BADGE_RED, 0.0).convert("RGBA")

    top_full = full.getpixel((32, 8))
    top_empty = empty.getpixel((32, 8))
    top_half = half.getpixel((32, 8))
    bottom_half = half.getpixel((32, 56))

    check(
        "满水位时整个背景带淡蓝",
        top_full[2] > top_empty[2],
        f"full={top_full} empty={top_empty}",
    )
    check(
        "半水位时上半仍为黑色",
        top_half == top_empty,
        f"half_top={top_half} empty={top_empty}",
    )
    check(
        "半水位时下半已有水色",
        bottom_half[2] > top_empty[2],
        f"half_bottom={bottom_half}",
    )

    def _has(im, pred) -> bool:
        raw = im.tobytes()
        return any(
            pred(raw[i], raw[i + 1], raw[i + 2], raw[i + 3])
            for i in range(0, len(raw), 4)
        )

    def has_red(im) -> bool:
        return _has(im, lambda r, g, b, a: a > 100 and r > 150 and g < 90 and b < 90)

    def has_blue(im) -> bool:
        return _has(im, lambda r, g, b, a: a > 200 and b > 40 and r < 40)

    number_only = create_balance_badge_icon("20", BADGE_RED, 1.0, "number").convert("RGBA")
    water_only = create_balance_badge_icon("20", BADGE_RED, 1.0, "water").convert("RGBA")

    check(
        "仅数字：有数字、无水位",
        has_red(number_only) and not has_blue(number_only),
    )
    check(
        "仅水位：有水位、无数字",
        has_blue(water_only) and not has_red(water_only),
    )
    check(
        "数字+水位：两者都在",
        has_blue(full) and has_red(full),
    )

    outlined = create_balance_badge_icon(
        "20", BADGE_RED, 1.0, "both", alert=True
    ).convert("RGBA")
    plain = create_balance_badge_icon(
        "20", BADGE_RED, 1.0, "both", alert=False
    ).convert("RGBA")
    edge_out = outlined.getpixel((32, 6))
    edge_plain = plain.getpixel((32, 6))
    check(
        "闪烁帧带红色描边",
        edge_out[0] > 150 and edge_out[1] < 110,
        f"edge={edge_out}",
    )
    check(
        "非闪烁帧没有红色描边",
        not (edge_plain[0] > 150 and edge_plain[1] < 110),
        f"edge={edge_plain}",
    )


# ---------------------------------------------------------------------------
# 测试 3：信号 -> 通知 + 闪烁
# ---------------------------------------------------------------------------

def test_signal_to_flash() -> None:
    section("Test 3: 信号文件 -> 安静期 -> 通知 + 图标闪烁")

    import src.app as appmod
    from src.config import Config
    from src.signal_monitor import check_signal, ensure_signal_dir

    cfg = Config()
    ensure_signal_dir(cfg)
    signal_file = cfg.signal_dir / "codex_complete.signal"

    check("初始无信号文件", check_signal(cfg) is False)
    signal_file.touch()
    check("信号被识别并删除", check_signal(cfg) is True and not signal_file.exists())

    notified: list[tuple] = []
    appmod.notify_task_complete = lambda sound=True, toast=True: notified.append((sound, toast))

    def make_app(**settings):
        app = appmod.App()
        app.cfg.set("notify_quiet_seconds", 10)
        app.cfg.set("flash_enabled", True)
        app.cfg.set("task_toast_enabled", True)
        for key, value in settings.items():
            app.cfg.set(key, value)
        app._schedule_flash_tick = lambda: None   # 确定性：不启动真实定时器
        app._last_poll = 10 ** 12                 # 本 tick 跳过余额轮询
        return app

    app = make_app()
    app.tray.set_balance(20.56)

    # 1) 收到活动信号后先进入安静期，不立即通知
    signal_file.touch()
    app._tick()
    check("收到活动信号时不立即通知", notified == [], str(notified))
    check("进入待确认状态", app._notify_pending is True)

    # 2) 安静期内又来一条中间回复，继续等待
    app._last_activity -= 5
    signal_file.touch()
    app._tick()
    check("中间回复会重置安静期", notified == [], str(notified))

    # 3) 安静期结束才通知
    app._last_activity -= 11
    app._tick()
    check("安静期结束后才通知", notified == [(True, True)], str(notified))
    check("任务完成开始闪烁", app._flashing is True)

    frames: list[bool] = []
    original_update = app.tray._update
    app.tray._update = lambda img: (original_update(img), frames.append(img is app.tray._alert_img))
    for _ in range(4):
        app._flash_tick()
    check("闪烁在 徽标/描边 之间交替", frames == [True, False, True, False], str(frames))
    app._cancel_flash()
    check("停止闪烁后恢复余额徽标", app.tray._current_img is app.tray._normal_img)

    # 4) 关闭闪烁：仍然通知，但不闪
    no_flash = make_app(flash_enabled=False)
    signal_file.touch()
    no_flash._tick()
    no_flash._last_activity -= 11
    no_flash._tick()
    check("关闭闪烁后不再闪烁", no_flash._flashing is False)

    # 5) 关闭弹窗：sound 仍为 True，toast 为 False
    no_toast = make_app(task_toast_enabled=False, flash_enabled=False)
    signal_file.touch()
    no_toast._tick()
    no_toast._last_activity -= 11
    no_toast._tick()
    check("关闭弹窗后 toast=False", notified[-1] == (True, False), str(notified[-1]))

# ---------------------------------------------------------------------------
# 测试 5：提供商解析
# ---------------------------------------------------------------------------

def test_providers() -> None:
    section("Test 5: 提供商解析")

    from src.providers import get_provider
    from src.providers.custom import CustomProvider, _dig
    from src.providers.moonshot import MoonshotProvider
    from src.providers.openai import OpenAIProvider

    moonshot = MoonshotProvider().parse_response({
        "code": 0,
        "status": True,
        "data": {
            "available_balance": 88.5,
            "voucher_balance": 20.0,
            "cash_balance": 68.5,
        },
    })
    check(
        "Moonshot 余额解析",
        moonshot.ok and moonshot.balance == 88.5 and moonshot.granted == 20.0,
        str(moonshot),
    )

    class _Cfg:
        def __init__(self, **kw):
            self._d = kw

        def get(self, key, default=None):
            return self._d.get(key, default)

    custom = CustomProvider(_Cfg(
        custom_api_url="https://example.com/balance",
        custom_json_path="data.wallet.balance",
        custom_currency="USD",
    ))
    parsed = custom.parse_response({"data": {"wallet": {"balance": "12.34"}}})
    check(
        "自定义提供商按字段路径解析",
        parsed.ok and parsed.balance == 12.34 and parsed.currency == "USD",
        str(parsed),
    )
    check(
        "字段路径不存在时返回错误",
        not CustomProvider(_Cfg(custom_json_path="data.nope"))
        .parse_response({"data": {}}).ok,
    )
    check("_dig 支持嵌套路径", _dig({"a": {"b": {"c": 7}}}, "a.b.c") == 7)
    check(
        "未配置自定义地址时报错",
        "custom_api_url" in (CustomProvider(_Cfg()).check("x").error or ""),
    )

    costs_payload = {
        "object": "page",
        "data": [
            {"object": "bucket", "start_time": 0, "end_time": 86400,
             "results": [{"object": "organization.costs.result",
                          "amount": {"value": 0.06, "currency": "usd"}}]},
            {"object": "bucket", "start_time": 86400, "end_time": 172800,
             "results": [{"object": "organization.costs.result",
                          "amount": {"value": 1.23, "currency": "usd"}}]},
        ],
        "has_more": False,
        "next_page": None,
    }
    openai = OpenAIProvider(_Cfg(openai_initial_balance=100.0)).parse_response(costs_payload)
    check(
        "OpenAI 剩余 = 初始 - 已花（美元）",
        openai.kind == "balance" and openai.currency == "USD"
        and abs(openai.spent - 1.29) < 1e-9
        and abs(openai.balance - 98.71) < 1e-9,
        str(openai),
    )
    over = OpenAIProvider(_Cfg(openai_initial_balance=1.0)).parse_response(costs_payload)
    check(
        "花费超过初始余额时剩余为负",
        abs(over.balance + 0.29) < 1e-9,
        str(over),
    )
    from src.providers.openai import _parse_date
    check("统计起始日期解析", _parse_date("2024-06-01") > 0 and _parse_date("") == 0)

    try:
        get_provider("not-exists")
        check("未知提供商抛错", False)
    except ValueError:
        check("未知提供商抛错", True)


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# 测试 4：WSL hook 安装脚本
# ---------------------------------------------------------------------------

def _bash_backend():
    """
    返回 (to_posix, run)，或 None（没有可用的 bash）。

    - Linux / WSL：直接用本机 bash，路径原样。
    - Windows：项目在 D:/C: 上，本机 bash 会是 git-bash 或缺失，所以通过
      wsl.exe 委托给 WSL 执行，并把 Windows 路径翻译成 /mnt/... 形式。
    """
    if os.name != "nt":
        bash = shutil.which("bash")
        if not bash:
            return None

        def to_posix(p: Path):
            return str(p)

        def run(code: str):
            return subprocess.run([bash, "-c", code], capture_output=True, text=True)

        return to_posix, run

    wsl = shutil.which("wsl.exe") or shutil.which("wsl")
    if not wsl:
        return None

    wsl_usable = True   # 探测过一次失败就不再重复等超时

    def to_posix(p: Path):
        nonlocal wsl_usable
        if not wsl_usable:
            return None
        try:
            proc = subprocess.run(
                [wsl, "-e", "wslpath", "-a", str(p)],
                capture_output=True, text=True, timeout=20,
            )
        except Exception:
            wsl_usable = False
            return None
        out = (proc.stdout or "").strip()
        if proc.returncode == 0 and out.startswith("/"):
            return out
        wsl_usable = False
        return None

    def run(code: str):
        return subprocess.run([wsl, "-e", "bash", "-c", code], capture_output=True, text=True)

    return to_posix, run


def test_hook_installer() -> None:
    section("Test 4: Codex 回合结束钩子安装")

    backend = _bash_backend()
    if backend is None:
        print("  [SKIP] 没有可用的 bash（Windows 上需要 WSL），跳过")
        return
    to_posix, run = backend

    tmp = Path(tempfile.mkdtemp(prefix="vb_hook_"))
    fake_home = tmp / "home"
    fake_home.mkdir(parents=True, exist_ok=True)
    fake_codex = tmp / "codex"
    fake_codex.mkdir(parents=True, exist_ok=True)
    signal_dir = tmp / "signal"
    signal_dir.mkdir(parents=True, exist_ok=True)

    # 旧 shell hook，安装后应被清理
    (fake_home / ".bashrc").write_text(
        "export FOO=1\n"
        "# >>> VisualizeBalance Codex Hook >>>\nold hook\n"
        "# <<< VisualizeBalance Codex Hook <<<\n",
        encoding="utf-8",
    )
    # 已有表头，用来验证 notify 被插到第一个 [table] 之前
    (fake_codex / "config.toml").write_text(
        'model = "test"\n\n[tui]\nfoo = 1\n', encoding="utf-8"
    )

    posix_home = to_posix(fake_home)
    posix_codex = to_posix(fake_codex)
    posix_sig = to_posix(signal_dir)
    posix_script = to_posix(ROOT / "scripts" / "install_wsl_hook.sh")
    if not (posix_home and posix_codex and posix_sig and posix_script):
        print("  [SKIP] 无法把路径传给 bash（项目不在 /mnt/c 或 /mnt/d 下？）")
        return

    q = shlex.quote
    cmd = "HOME={h} CODEX_HOME={c} VB_SIGNAL_DIR={s} bash {sc}".format(
        h=q(posix_home), c=q(posix_codex), s=q(posix_sig), sc=q(posix_script)
    )
    proc = run(cmd)
    if proc.returncode != 0:
        print("  ---- 安装脚本输出 ----")
        print((proc.stdout or "") + (proc.stderr or ""))
    check("安装脚本正常退出", proc.returncode == 0,
          (proc.stderr or proc.stdout).strip()[:120])

    notify = fake_home / ".visualize_balance" / "codex_notify.sh"
    check("通知脚本已安装", notify.is_file())

    cfg_text = (fake_codex / "config.toml").read_text(encoding="utf-8")
    expected_path = posix_home.rstrip("/") + "/.visualize_balance/codex_notify.sh"
    check(
        'config.toml 写入 notify = ["bash", ...]',
        'notify = ["bash"' in cfg_text and expected_path in cfg_text,
        cfg_text.replace("\n", " | ")[:160],
    )
    check(
        "notify 位于第一个 [table] 之前",
        "notify =" in cfg_text and cfg_text.index("notify =") < cfg_text.index("[tui]"),
    )
    check(
        "旧 shell hook 已清理",
        "VisualizeBalance Codex Hook"
        not in (fake_home / ".bashrc").read_text(encoding="utf-8"),
    )

    posix_notify = to_posix(notify)
    if not posix_notify:
        print("  [SKIP] 无法翻译通知脚本路径，跳过实跑")
        return

    signal_file = signal_dir / "codex_complete.signal"

    def fire(payload: str):
        return run(
            "HOME={h} VB_SIGNAL_DIR={s} bash {n} {p}".format(
                h=q(posix_home), s=q(posix_sig), n=q(posix_notify), p=q(payload)
            )
        )

    early = '{"type":"agent-turn-complete","turn-id":"t0","last-assistant-message":""}'
    fire(early)
    check("只有回合完成事件、但还没输出时，不通知", not signal_file.exists())

    other = '{"type":"session-start","turn-id":"t1"}'
    fire(other)
    check("非回合完成事件不通知", not signal_file.exists())

    done = (
        '{"type":"agent-turn-complete","turn-id":"t1","cwd":"/x",'
        '"input-messages":["hi"],"last-assistant-message":"hello"}'
    )
    fire(done)
    check("回合完成且有助手输出时才写信号", signal_file.exists())

    if signal_file.exists():
        signal_file.unlink()
    fire(done)
    check("同一 turn-id 只通知一次", not signal_file.exists())

    spaced = '{"type": "turn-complete", "turn-id": "t2", "last-assistant-message": "ok"}'
    fire(spaced)
    check("新版 turn-complete 事件也能识别", signal_file.exists())

    if signal_file.exists():
        signal_file.unlink()
    title = (
        '{"type":"agent-turn-complete","turn-id":"t3",'
        '"input-messages":["Generate a concise, single-line task title of at most'
        ' 36 characters..."],"last-assistant-message":"{\\"title\\":\\"x\\"}"}'
    )
    fire(title)
    check("线程标题生成这类内部回合不通知", not signal_file.exists())

    recap = (
        '{"type":"agent-turn-complete","turn-id":"t4",'
        '"input-messages":["Write a brief catch-up for a user returning to this'
        ' task. Return JSON with summary..."],"last-assistant-message":"..."}'
    )
    fire(recap)
    check("会话摘要这类内部回合不通知", not signal_file.exists())

    check(
        "调用记录写入 notify.log",
        (fake_home / ".visualize_balance" / "notify.log").is_file(),
    )


# ---------------------------------------------------------------------------

def main() -> int:
    print("=" * 60)
    print("  VisualizeBalance — 冒烟测试")
    print("=" * 60)

    workdir = Path(tempfile.mkdtemp(prefix="vb_smoke_"))
    os.environ["USERPROFILE"] = str(workdir)
    os.environ["APPDATA"] = str(workdir / "appdata")
    os.environ.pop("DEEPSEEK_API_KEY", None)

    _install_stubs()
    sys.path.insert(0, str(ROOT))

    test_badge_spec()
    test_badge_render()
    test_signal_to_flash()
    test_providers()
    test_hook_installer()

    failed = [name for name, ok, _ in _RESULTS if not ok]
    print("\n" + "=" * 60)
    if failed:
        print(f"  结果: FAIL（{len(failed)}/{len(_RESULTS)} 项未通过）")
        for name in failed:
            print(f"    - {name}")
        return 1
    print(f"  结果: PASS（{len(_RESULTS)} 项全部通过）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
