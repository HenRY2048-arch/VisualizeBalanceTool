"""配置管理 — JSON 文件 + 环境变量回退"""

import json
import logging
import os
from pathlib import Path

log = logging.getLogger(__name__)

# 配置文件路径：%APPDATA%/VisualizeBalance/config.json
_CONFIG_DIR = Path(os.environ.get("APPDATA", Path.home())) / "VisualizeBalance"
CONFIG_PATH = _CONFIG_DIR / "config.json"

# 默认值
_DEFAULTS: dict = {
    "provider": "deepseek",
    "api_key": "",
    "alert_threshold": 1.0,
    "poll_interval": 120,
    "signal_poll_interval": 2,
    "flash_interval": 500,
    "flash_timeout": 30000,
    "sound_enabled": True,
    "auto_start": False,
    # 托盘余额徽标的配色阈值（按余额零头 0.xx 判定）
    "badge_green_at": 0.50,   # 零头 >= 此值 -> 草绿
    "badge_red_below": 0.25,  # 零头 <  此值 -> 红；介于两者之间 -> 橙
}


def _as_float(value, fallback: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _sanitize_badge_thresholds(data: dict) -> None:
    """
    保证 0 <= badge_red_below < badge_green_at <= 1。

    配置文件是可以被手工编辑的，这里做一次兜底，避免出现“既红又绿”的配置。
    不满足约束时整体回退到默认值。
    """
    red = _as_float(data.get("badge_red_below"), _DEFAULTS["badge_red_below"])
    green = _as_float(data.get("badge_green_at"), _DEFAULTS["badge_green_at"])
    red = min(max(red, 0.0), 1.0)
    green = min(max(green, 0.0), 1.0)
    if not red < green:
        red = _DEFAULTS["badge_red_below"]
        green = _DEFAULTS["badge_green_at"]
    data["badge_red_below"] = red
    data["badge_green_at"] = green


class Config:
    """
    配置管理器。
    读取顺序：config.json → 环境变量回退 → 默认值。
    """

    def __init__(self) -> None:
        self._data: dict = dict(_DEFAULTS)
        self._load()

    # ------------------------------------------------------------------
    # 读取
    # ------------------------------------------------------------------

    def get(self, key: str, default=None):
        """读取配置项"""
        return self._data.get(key, default)

    def __getattr__(self, key: str):
        if key.startswith("_"):
            return super().__getattribute__(key)
        if key in self._data:
            return self._data[key]
        raise AttributeError(f"Config 无此配置项: {key}")

    # ------------------------------------------------------------------
    # 写入
    # ------------------------------------------------------------------

    def set(self, key: str, value) -> None:
        self._data[key] = value

    def save(self) -> None:
        """持久化到 config.json"""
        try:
            _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            CONFIG_PATH.write_text(
                json.dumps(self._data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            log.info("配置已保存: %s", CONFIG_PATH)
        except OSError as exc:
            log.error("配置保存失败: %s", exc)

    def reload(self) -> None:
        """重新从磁盘加载"""
        self._data = dict(_DEFAULTS)
        self._load()

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _load(self) -> None:
        # 1. 从 JSON 文件加载
        if CONFIG_PATH.exists():
            try:
                saved = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
                self._data.update(saved)
                log.info("已加载配置: %s", CONFIG_PATH)
            except (json.JSONDecodeError, OSError) as exc:
                log.warning("配置文件读取失败: %s，使用默认值", exc)

        # 2. 环境变量回退（JSON 中没有的 key，从环境变量补）
        env_map = {
            "api_key": "DEEPSEEK_API_KEY",
            "alert_threshold": "VB_ALERT_THRESHOLD",
            "poll_interval": "VB_POLL_INTERVAL",
            "signal_poll_interval": "VB_SIGNAL_POLL_INTERVAL",
            "flash_interval": "VB_FLASH_INTERVAL",
            "flash_timeout": "VB_FLASH_TIMEOUT",
            "badge_green_at": "VB_BADGE_GREEN_AT",
            "badge_red_below": "VB_BADGE_RED_BELOW",
        }
        for config_key, env_key in env_map.items():
            env_val = os.environ.get(env_key)
            if env_val is not None and self._data.get(config_key) in (None, "", _DEFAULTS.get(config_key)):
                try:
                    default = _DEFAULTS[config_key]
                    if isinstance(default, float):
                        self._data[config_key] = float(env_val)
                    elif isinstance(default, int):
                        self._data[config_key] = int(env_val)
                    else:
                        self._data[config_key] = env_val
                    log.info("从环境变量加载: %s = %s", config_key, env_val[:20] if isinstance(env_val, str) else env_val)
                except (ValueError, TypeError):
                    pass

        # 3. 兜底校正配色阈值
        _sanitize_badge_thresholds(self._data)

    @property
    def signal_dir(self) -> Path:
        """信号文件目录"""
        win_home = os.environ.get("USERPROFILE", "")
        base = Path(win_home) if win_home else Path.home()
        return base / ".visualize_balance" / "signal"
