"""
PyInstaller 构建脚本 — 打包成带图标的单文件 .exe
用法：python scripts/build.py
产物：dist/VisualizeBalance.exe
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def build() -> None:
    print("=" * 50)
    print("  VisualizeBalance — Build .exe")
    print("=" * 50)

    icon_path = ROOT / "assets" / "icon_normal.ico"
    if not icon_path.exists():
        print(f"Warning: icon not found at {icon_path}, using default")

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--noconsole",
        "--name", "VisualizeBalance",
        "--add-data", f"{ROOT / 'assets'};assets",
        "--hidden-import", "pystray._win32",
        "--hidden-import", "PIL._tkinter_finder",
    ]

    if icon_path.exists():
        cmd += ["--icon", str(icon_path)]

    cmd.append(str(ROOT / "run.py"))

    print(f"\nRunning: {' '.join(cmd)}\n")
    result = subprocess.run(cmd, cwd=str(ROOT))
    if result.returncode == 0:
        exe = ROOT / "dist" / "VisualizeBalance.exe"
        print(f"\nDone! Output: {exe}")
    else:
        print(f"\nFailed (exit {result.returncode})")
        sys.exit(result.returncode)


if __name__ == "__main__":
    build()
