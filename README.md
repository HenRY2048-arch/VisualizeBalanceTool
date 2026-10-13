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

