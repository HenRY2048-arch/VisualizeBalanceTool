# VisualizeBalanceTool

# Provide timely token balance inquiries and task completion notifications.

# VisualizeBalance

DeepSeek API balance monitor and Codex CLI task completion notification — a Windows system tray utility.

## Features

* **Balance monitoring**: Polls DeepSeek API every 2 minutes, displays balance in system tray tooltip
* **Balance badge icon**: The tray icon is a small black box showing the balance (max 2 digits).
The digit color tracks the fractional remainder, with thresholds you can change in
Settings: remainder `>= green\_at` → grass green, `< red\_below` → red, in between → orange,
and a whole-number balance (e.g. `20.00`) → white. Defaults are `0.50` / `0.25`.
The application/exe icon is unchanged.
* **Low balance alert**: Icon flashes red + toast notification + sound when balance drops below threshold
* **Task completion notification**: Detects Codex CLI task completion via WSL2 signal files
* **Settings UI**: Configure API key, alert threshold, poll interval, badge color thresholds,
sound, and auto-start via GUI (no manual env var editing)
* **Installer/Uninstaller**: Inno Setup installer with classic wizard, creates shortcuts and uninstall entry
* **Extensible providers**: Add new API providers by implementing a single class

## Quick Start

### 1\. Install dependencies

```powershell
pip install -r requirements.txt
```

### 2\. Configure API key

Option A — Run the app, right-click the tray icon, click "Settings..." and enter your key.

Option B — Set environment variable (legacy, still supported as fallback):

```powershell
setx DEEPSEEK\_API\_KEY "sk-xxxxxxxx"
```

### 3\. Run (development mode)

```powershell
python run.py
```

### 4\. Build .exe

项目如果在 WSL 里开发、打包却在 Windows 上做，先把源码同步到本地磁盘
（别在 `\\\\wsl$\\...` 这类 UNC 路径下直接跑 pip / PyInstaller）：

```bash
bash scripts/sync\_to\_windows.sh                     # 默认 -> /mnt/d/visualizeBalance
bash scripts/sync\_to\_windows.sh /mnt/e/vb           # 自定义目标
```

脚本不会同步 `.git`、`\_\_pycache\_\_`、`dist`、`build`、`\*.spec`、`scripts/Output`，
并且会拒绝同步到 `/mnt/d` 这类盘符根目录。目标已存在但不像本项目时会中止，
确认无误可加 `--force`。

然后在 Windows 侧：

```powershell
cd D:\\visualizeBalance
powershell -ExecutionPolicy Bypass -File scripts\\rebuild.ps1
```

`rebuild.ps1` 一条命令跑完「依赖 + exe + 安装包」，也可以分步来：

```powershell
python scripts\\build.py
```

（`-SkipDeps` 跳过依赖安装，`-SkipInstaller` 只出 exe。）

### 5\. Create desktop shortcut

```powershell
powershell -ExecutionPolicy Bypass -File scripts\\create\_shortcut.ps1
```

### 6\. Build installer (requires Inno Setup 5)

Open `scripts\\build.iss` in Inno Setup Compiler and click Build, or:

```powershell
\& "C:\\Program Files (x86)\\Inno Setup 5\\iscc.exe" scripts\\build.iss
```

Output: `scripts\\Output\\VisualizeBalance-Setup.exe`

### 7\. Install WSL2 hook (optional)

```bash
bash scripts/install\_wsl\_hook.sh
source \~/.bashrc      # 或 \~/.zshrc，脚本会打印实际目标文件
```

脚本按以下顺序决定写哪个 rc 文件：`VB\_SHELL` 环境变量 → 登录 shell
（`getent passwd`）→ 兜底（哪个 shell 装了用哪个，优先 bash）。登录 shell 是
zsh 但 zsh 未安装时会自动回退到 bash。检测到 hook 装在“非目标 shell”里时会
提示清理，`VB\_PURGE\_STALE=1 bash scripts/install\_wsl\_hook.sh` 可自动清理。

### 8\. Smoke test

```bash
python scripts/smoke\_test.py
```

校验余额徽标配色规则、徽标渲染、信号→通知→图标闪烁链路，以及 WSL hook 安装
脚本本身（需要 bash）。缺依赖时会自动打桩，纯 Linux/WSL 环境也能跑。

## Project Structure

```
visualizeBalance/
├── run.py                    # Entry point
├── requirements.txt          # Python dependencies
├── src/
│   ├── \_\_init\_\_.py
│   ├── main.py               # Logging init and entry function
│   ├── app.py                # Main app orchestrator
│   ├── config.py             # JSON config + env var fallback
│   ├── settings.py           # tkinter settings window
│   ├── notification.py       # Sound + toast notifications
│   ├── signal\_monitor.py     # WSL2 signal file listener
│   ├── tray.py               # System tray icon manager
│   ├── icons.py              # Icon generator/loader
│   └── providers/
│       ├── \_\_init\_\_.py       # Provider registry
│       ├── base.py           # Abstract base class
│       └── deepseek.py       # DeepSeek implementation
├── assets/                   # Icons and sound files
├── scripts/
│   ├── build.py              # PyInstaller build script
│   ├── build.iss             # Inno Setup installer script
│   ├── create\_shortcut.ps1   # Desktop shortcut creator
│   ├── install\_wsl\_hook.sh   # WSL2 hook installer
│   └── smoke\_test.py         # Headless smoke test
└── dist/                     # Build output
```

## Uninstall \& Cleanup

1. 通过安装包卸载（推荐）：`设置 → 应用 → VisualizeBalance → 卸载`，
或直接运行安装目录里的 `unins000.exe`。这会删除程序文件、开始菜单/桌面
快捷方式，并清掉 Inno Setup 的注册表卸载项。
2. 手动清理残留（卸载器不会碰这些用户数据）：

```
%APPDATA%\\VisualizeBalance\\                 # config.json
%USERPROFILE%\\.visualize\_balance\\           # 信号目录
%APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs\\Startup\\VisualizeBalance.lnk
HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run  ->  删除 VisualizeBalance
```

3. 清理 WSL 里的 hook：删除 `\~/.bashrc`/`\~/.zshrc` 中
`VisualizeBalance Codex Hook >>>` 到 `<<< VisualizeBalance Codex Hook`
之间的内容。

## Configuration

Settings are stored in `%APPDATA%\\VisualizeBalance\\config.json`:

```json
{
  "provider": "deepseek",
  "api\_key": "sk-xxxxxxxx",
  "alert\_threshold": 1.0,
  "poll\_interval": 120,
  "badge\_green\_at": 0.5,
  "badge\_red\_below": 0.25,
  "sound\_enabled": true,
  "auto\_start": false
}
```

All settings can also be overridden by environment variables (see config.py for mapping).

## Adding a New Provider

1. Create `src/providers/your\_provider.py`
2. Implement `BaseProvider` (see `deepseek.py` for reference)
3. Register with `@register` decorator
4. Add to `src/providers/\_\_init\_\_.py` imports
5. Add to `src/settings.py` provider dropdown

## License

MIT

