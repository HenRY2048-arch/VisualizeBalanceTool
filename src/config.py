"""配置管理 — JSON 文件 + 环境变量回退"""

import copy
import json
import logging
import os
import re
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
    # 托盘数字颜色分段。每段 at 为起始值（含），color 为 #RRGGBB。
    # 十位级（<100）按零头 0~1 判定，最多 10 段。
    "badge_bands": [
        {"at": 0.0, "color": "#FF0000"},
        {"at": 0.25, "color": "#FFA500"},
        {"at": 0.50, "color": "#7CFC00"},
    ],
    # 百元级（>=100）按绝对金额判定，最多 20 段。
    "badge_hundreds_bands": [
        {"at": 0.0, "color": "#FF0000"},
        {"at": 320.0, "color": "#FFA500"},
        {"at": 360.0, "color": "#7CFC00"},
    ],
    # 余额正好是整数时的数字颜色
    "badge_integer_color": "#FFFFFF",
    # 托盘徽标显示方式：both / number / water
    "badge_display_mode": "both",
    # 水位格的单位（元，必须为正整数）
    "badge_water_unit": 1,
    # 任务完成时的行为开关
    "flash_enabled": True,        # 是否闪烁托盘图标
    "task_toast_enabled": True,   # 是否弹任务完成 Toast
}


def _as_float(value, fallback: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _as_bool(value, fallback: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        v = value.strip().lower()
        if v in ("true", "1", "yes", "on"):
            return True
        if v in ("false", "0", "no", "off"):
            return False
    return fallback


_HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
MAX_FRACTION_BANDS = 10
MAX_HUNDREDS_BANDS = 20


def _normalize_color(value, fallback: str) -> str:
    if isinstance(value, str) and _HEX_COLOR_RE.match(value.strip()):
        return value.strip().upper()
    return fallback


def _sanitize_bands(value, fallback: list, low: float, high: float,
                    limit: int) -> list:
    """
    校验颜色分段：必须是非空列表，最多 limit 段，每段含合法 at 与 #RRGGBB 颜色。
    任意一项非法就整体回退默认值；首段自动补齐到 low，保证所有取值都有颜色。
    """
    if not isinstance(value, list) or not value:
        return copy.deepcopy(fallback)

    out = []
    for item in value[:limit]:
        if not isinstance(item, dict):
            return copy.deepcopy(fallback)
        try:
            at = float(item.get("at"))
        except (TypeError, ValueError):
            return copy.deepcopy(fallback)
        color = item.get("color")
        if at < low or at > high:
            return copy.deepcopy(fallback)
        if not isinstance(color, str) or not _HEX_COLOR_RE.match(color.strip()):
            return copy.deepcopy(fallback)
        out.append({"at": round(at, 4), "color": color.strip().upper()})

    out.sort(key=lambda b: b["at"])
    dedup = []
    for band in out:
        if dedup and abs(dedup[-1]["at"] - band["at"]) < 1e-9:
            dedup[-1] = band
        else:
            dedup.append(band)
    if not dedup:
        return copy.deepcopy(fallback)
    if dedup[0]["at"] > low:
        dedup.insert(0, {"at": low, "color": dedup[0]["color"]})
    return dedup[:limit]


def _migrate_legacy_bands(saved: dict) -> None:
    """把旧版的 4 个阈值键转换为颜色分段。"""
    if "badge_bands" not in saved and (
        "badge_red_below" in saved or "badge_green_at" in saved
    ):
        red = _as_float(saved.get("badge_red_below"), 0.25)
        green = _as_float(saved.get("badge_green_at"), 0.50)
        saved["badge_bands"] = [
            {"at": 0.0, "color": "#FF0000"},
            {"at": red, "color": "#FFA500"},
            {"at": green, "color": "#7CFC00"},
        ]
    if "badge_hundreds_bands" not in saved and (
        "badge_hundreds_red_below" in saved or "badge_hundreds_green_at" in saved
    ):
        red = _as_float(saved.get("badge_hundreds_red_below"), 320.0)
        green = _as_float(saved.get("badge_hundreds_green_at"), 360.0)
        saved["badge_hundreds_bands"] = [
            {"at": 0.0, "color": "#FF0000"},
            {"at": red, "color": "#FFA500"},
            {"at": green, "color": "#7CFC00"},
        ]


def _sanitize_badge_thresholds(data: dict) -> None:
    """
    配置文件可以被手工编辑，这里做一次兜底，避免出现“既红又绿”的配置。

    - 十元级（<100）：阈值是零头 0~1
    - 百元级（>=100）：阈值是绝对金额
    """
    data["badge_bands"] = _sanitize_bands(
        data.get("badge_bands"), _DEFAULTS["badge_bands"],
        0.0, 1.0, MAX_FRACTION_BANDS,
    )
    data["badge_hundreds_bands"] = _sanitize_bands(
        data.get("badge_hundreds_bands"), _DEFAULTS["badge_hundreds_bands"],
        0.0, 1e9, MAX_HUNDREDS_BANDS,
    )
    data["badge_integer_color"] = _normalize_color(
        data.get("badge_integer_color"), _DEFAULTS["badge_integer_color"]
    )

    mode = str(data.get("badge_display_mode", "both")).strip().lower()
    if mode not in ("both", "number", "water"):
        mode = _DEFAULTS["badge_display_mode"]
    data["badge_display_mode"] = mode

    try:
        unit_f = float(data.get("badge_water_unit", 1))
        unit = int(unit_f)
        if unit_f != unit or unit < 1:
            unit = _DEFAULTS["badge_water_unit"]
    except (TypeError, ValueError):
        unit = _DEFAULTS["badge_water_unit"]
    data["badge_water_unit"] = unit

    for flag in ("flash_enabled", "task_toast_enabled"):
        data[flag] = _as_bool(data.get(flag), _DEFAULTS[flag])


class Config:
    """
    配置管理器。
    读取顺序：config.json → 环境变量回退 → 默认值。
    """

    def __init__(self) -> None:
        self._data: dict = copy.deepcopy(_DEFAULTS)
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
        self._data = copy.deepcopy(_DEFAULTS)
        self._load()

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _load(self) -> None:
        # 1. 从 JSON 文件加载
        if CONFIG_PATH.exists():
            try:
                saved = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
                _migrate_legacy_bands(saved)
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
            "badge_integer_color": "VB_BADGE_INTEGER_COLOR",
            "badge_display_mode": "VB_BADGE_DISPLAY_MODE",
            "badge_water_unit": "VB_BADGE_WATER_UNIT",
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
