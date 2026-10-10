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
        tk.ttk = ttk
        tk.messagebox = messagebox
        sys.modules.update({
            "tkinter": tk,
            "tkinter.ttk": ttk,
            "tkinter.messagebox": messagebox,
        })


# ---------------------------------------------------------------------------
# 测试 1：配色规则
# ---------------------------------------------------------------------------

def test_badge_spec() -> None:
    from src.icons import (
        BADGE_GREEN,
        BADGE_GREEN_AT_DEFAULT,
        BADGE_ORANGE,
        BADGE_RED,
        BADGE_RED_BELOW_DEFAULT,
        BADGE_WHITE,
        balance_badge_spec,
    )

    section("Test 1: 余额徽标配色规则")
    cases = [
        (20.00, "20", BADGE_WHITE, "整数余额 20.00 -> 白"),
        (0.00, "0", BADGE_WHITE, "0.00 -> 白"),
        (20.08, "20", BADGE_RED, "零头 0.08 < 0.25 -> 红"),
        (20.25, "20", BADGE_ORANGE, "零头 = 0.25（红色阈值边界）-> 橙"),
        (20.43, "20", BADGE_ORANGE, "零头 0.43 -> 橙"),
        (20.50, "20", BADGE_GREEN, "零头 = 0.50（绿色阈值边界）-> 绿"),
        (20.56, "20", BADGE_GREEN, "零头 0.56 >= 0.50 -> 绿"),
        (99.99, "99", BADGE_GREEN, "99.99 -> 两位数 99"),
        (8.96, "8", BADGE_GREEN, "一位数余额"),
        (123.45, "99", BADGE_ORANGE, ">99 封顶为 99"),
        (None, "--", BADGE_WHITE, "无余额 -> --"),
    ]
    for value, text, color, label in cases:
        got_text, got_color = balance_badge_spec(value)
        check(
            f"{label}（{value}）",
            got_text == text and got_color == color,
            f"期望 ({text}, {color}) 实际 ({got_text}, {got_color})",
        )

    # 自定义阈值：绿 0.30 / 红 0.10
    custom = [
        (20.05, BADGE_RED, "自定义阈值：零头 0.05 < 0.10 -> 红"),
        (20.15, BADGE_ORANGE, "自定义阈值：0.10 <= 零头 0.15 < 0.30 -> 橙"),
        (20.30, BADGE_GREEN, "自定义阈值：零头 0.30 >= 0.30 -> 绿"),
        (20.00, BADGE_WHITE, "自定义阈值下整数仍是白"),
    ]
    for value, color, label in custom:
        _, got_color = balance_badge_spec(value, green_at=0.30, red_below=0.10)
        check(label, got_color == color, f"期望 {color} 实际 {got_color}")

    # 配置默认值必须与 icons 里的默认阈值一致，避免两处漂移
    from src import config as config_mod

    cfg = config_mod.Config()
    check(
        "config 默认阈值与 icons 默认值一致",
        cfg.get("badge_green_at") == BADGE_GREEN_AT_DEFAULT
        and cfg.get("badge_red_below") == BADGE_RED_BELOW_DEFAULT,
        f"config=({cfg.get('badge_green_at')}, {cfg.get('badge_red_below')}) "
        f"icons=({BADGE_GREEN_AT_DEFAULT}, {BADGE_RED_BELOW_DEFAULT})",
    )

    # 手工写坏 config.json 时，兜底必须回到默认值
    config_mod.CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    config_mod.CONFIG_PATH.write_text(
        '{"badge_green_at": 0.2, "badge_red_below": 0.8}', encoding="utf-8"
    )
    broken = config_mod.Config()
    check(
        "非法阈值组合（红 > 绿）被兜底为默认值",
        broken.get("badge_green_at") == BADGE_GREEN_AT_DEFAULT
        and broken.get("badge_red_below") == BADGE_RED_BELOW_DEFAULT,
        f"期望默认值，实际 ({broken.get('badge_green_at')}, {broken.get('badge_red_below')})",
    )
    config_mod.CONFIG_PATH.unlink()


# ---------------------------------------------------------------------------
# 测试 2：徽标渲染
# ---------------------------------------------------------------------------

def test_badge_render() -> None:
    from src.icons import BADGE_RED, create_balance_badge_icon

    section("Test 2: 徽标图标渲染")
    img = create_balance_badge_icon("20", BADGE_RED)
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


# ---------------------------------------------------------------------------
# 测试 3：信号 -> 通知 + 闪烁
# ---------------------------------------------------------------------------

def test_signal_to_flash() -> None:
    section("Test 3: 信号文件 -> 通知 + 图标闪烁")

    import src.app as appmod
    from src.config import Config
    from src.signal_monitor import check_signal, ensure_signal_dir

    cfg = Config()
    ensure_signal_dir(cfg)
    signal_file = cfg.signal_dir / "codex_complete.signal"

    check("初始无信号文件", check_signal(cfg) is False)
    signal_file.touch()
    check("信号被识别并删除", check_signal(cfg) is True and not signal_file.exists())

    notified: list[bool] = []
    appmod.notify_task_complete = lambda sound=True: notified.append(sound)

    app = appmod.App()
    app._schedule_flash_tick = lambda: None      # 确定性：不启动真实定时器
    app._last_poll = 10 ** 12                    # 本 tick 跳过余额轮询
    app.tray.set_balance(20.56)

    signal_file.touch()
    app._tick()
    check("任务完成触发通知（含提示音）", notified == [True], str(notified))
    check("任务完成开始闪烁", app._flashing is True)

    frames: list[bool] = []
    original_update = app.tray._update
    app.tray._update = lambda img: (original_update(img), frames.append(img is app.tray._alert_img))
    for _ in range(4):
        app._flash_tick()
    check("闪烁在 徽标/告警 之间交替", frames == [True, False, True, False], str(frames))
    app._cancel_flash()
    check("停止闪烁后恢复余额徽标", app.tray._current_img is app.tray._normal_img)


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
    section("Test 4: WSL hook 安装脚本")

    backend = _bash_backend()
    if backend is None:
        print("  [SKIP] 没有可用的 bash（Windows 上需要 WSL），跳过")
        return
    to_posix, run = backend

    tmp = Path(tempfile.mkdtemp(prefix="vb_hook_"))
    fake_home = tmp / "home"
    fake_home.mkdir(parents=True, exist_ok=True)
    signal_dir = tmp / "signal"
    signal_dir.mkdir(parents=True, exist_ok=True)
    stale = fake_home / ".zshrc"
    stale.write_text(
        "# >>> VisualizeBalance Codex Hook >>>\nstale hook\n"
        "# <<< VisualizeBalance Codex Hook <<<\n",
        encoding="utf-8",
    )

    posix_home = to_posix(fake_home)
    posix_sig = to_posix(signal_dir)
    posix_script = to_posix(ROOT / "scripts" / "install_wsl_hook.sh")
    if not (posix_home and posix_sig and posix_script):
        print("  [SKIP] 无法把路径传给 bash（项目不在 /mnt/c 或 /mnt/d 下？）")
        return

    q = shlex.quote
    install_cmd = (
        "HOME={home} VB_SHELL=bash VB_SIGNAL_DIR={sig} VB_PURGE_STALE=1 bash {script}"
    ).format(home=q(posix_home), sig=q(posix_sig), script=q(posix_script))

    proc = run(install_cmd)
    if proc.returncode != 0:
        print("  ---- 安装脚本输出 ----")
        print((proc.stdout or "") + (proc.stderr or ""))
    check("安装脚本正常退出", proc.returncode == 0, (proc.stderr or proc.stdout).strip()[:120])

    bashrc = fake_home / ".bashrc"
    bashrc_text = bashrc.read_text(encoding="utf-8") if bashrc.exists() else ""
    check("hook 写入登录 shell 对应的 .bashrc", "VisualizeBalance Codex Hook" in bashrc_text)
    check("陈旧 .zshrc hook 被清理", "VisualizeBalance Codex Hook" not in stale.read_text(encoding="utf-8"))
    check("脚本内含 DEBUG 守卫", "_vb_*) return" in bashrc_text)

    if not bashrc_text:
        print("  [SKIP] .bashrc 未生成，跳过 hook 实跑")
        return

    posix_bashrc = to_posix(bashrc)
    if not posix_bashrc:
        print("  [SKIP] 无法翻译 .bashrc 路径，跳过 hook 实跑")
        return

    hook_cmd = (
        "set -eu; "
        "source <(sed -n '/VisualizeBalance Codex Hook >>>/,/VisualizeBalance Codex Hook <<</p' {rc}); "
        '_vb_last_cmd="codex"; _vb_precmd_hook; ls {sig}'
    ).format(rc=q(posix_bashrc), sig=q(posix_sig))

    proc2 = run(hook_cmd)
    check(
        "bash hook 能生成信号文件",
        "codex_complete.signal" in proc2.stdout,
        (proc2.stdout + proc2.stderr).strip()[:120],
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
