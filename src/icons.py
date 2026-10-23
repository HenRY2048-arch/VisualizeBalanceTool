"""程序化生成托盘图标，支持加载外部自定义图标"""

import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def _assets_dir() -> Path:
    """获取 assets 目录路径，兼容 PyInstaller 打包后的路径"""
    if getattr(sys, "_MEIPASS", None):
        return Path(sys._MEIPASS) / "assets"
    return Path(__file__).resolve().parent.parent / "assets"


def _load_external(name: str, size: int = 64) -> Image.Image | None:
    """尝试从 assets/ 加载外部 .ico 或 .png"""
    path = _assets_dir() / name
    if path.exists():
        img = Image.open(path).convert("RGBA")
        return img.resize((size, size), Image.Resampling.LANCZOS)
    return None


def _draw_text_icon(text: str, color: tuple, bg: tuple, size: int = 64) -> Image.Image:
    """绘制文字图标（后备方案）"""
    img = Image.new("RGBA", (size, size), bg)
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arial.ttf", size // 2)
    except (OSError, IOError):
        font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(((size - tw) / 2, (size - th) / 2 - 2), text, fill=color, font=font)
    return img


def create_normal_icon(size: int = 64) -> Image.Image:
    """正常状态图标 — 绿色 ¥ 符号"""
    return _load_external("icon_normal.ico", size) or _draw_text_icon(
        "¥", (255, 255, 255), (34, 139, 34), size
    )


def create_alert_icon(size: int = 64) -> Image.Image:
    """告警状态图标 — 红色 ¥ 符号"""
    return _load_external("icon_alert.ico", size) or _draw_text_icon(
        "¥", (255, 255, 255), (220, 20, 60), size
    )


def create_no_key_icon(size: int = 64) -> Image.Image:
    """未配置 API Key — 灰色 ⚠ 符号"""
    return _load_external("icon_alert.ico", size) or _draw_text_icon(
        "⚠", (255, 255, 255), (128, 128, 128), size
    )


# ---------------------------------------------------------------------------
# 托盘余额徽标：黑底矩形 + 余额数字
# ---------------------------------------------------------------------------

# 数字颜色
BADGE_GREEN = (124, 252, 0)    # 草绿
BADGE_ORANGE = (255, 165, 0)   # 橙
BADGE_RED = (255, 0, 0)        # 红
BADGE_WHITE = (255, 255, 255)  # 白（余额正好是整数时）
BADGE_BG = (0, 0, 0, 255)      # 黑底
# 水位：高透明度淡蓝（alpha 低，避免遮住数字）
BADGE_WATER = (0, 191, 255, 72)
# 闪烁时的红色描边
BADGE_ALERT_BORDER = (255, 59, 48)

BADGE_WATER_UNIT_DEFAULT = 1
BADGE_DISPLAY_MODE_DEFAULT = "both"

# 颜色分段上限：十位级最细 1 元 -> 10 段；百元级最细 5 元 -> 20 段
MAX_FRACTION_BANDS = 10
MAX_HUNDREDS_BANDS = 20
BADGE_INTEGER_COLOR_DEFAULT = "#FFFFFF"
BADGE_BANDS_DEFAULT = [
    {"at": 0.0, "color": "#FF0000"},
    {"at": 0.25, "color": "#FFA500"},
    {"at": 0.50, "color": "#7CFC00"},
]
BADGE_HUNDREDS_BANDS_DEFAULT = [
    {"at": 0.0, "color": "#FF0000"},
    {"at": 320.0, "color": "#FFA500"},
    {"at": 360.0, "color": "#7CFC00"},
]

# 水位量化档数：托盘只有 16~32px，按 1/32 档足够"大致体现"，也能减少重绘
WATER_LEVEL_STEPS = 32

# 优先使用加粗字体，缺失时逐个回退
_BADGE_FONTS = ("arialbd.ttf", "arial.ttf", "DejaVuSans-Bold.ttf")
_HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


def hex_to_rgb(value, fallback: tuple = BADGE_WHITE) -> tuple:
    """把 #RRGGBB 转成 (r, g, b)，非法值返回 fallback。"""
    if not isinstance(value, str) or not _HEX_COLOR_RE.match(value.strip()):
        return fallback
    raw = value.strip().lstrip("#")
    return tuple(int(raw[i:i + 2], 16) for i in (0, 2, 4))


def pick_band_color(value: float, bands) -> tuple:
    """在颜色分段中找出 value 所属段的颜色（取起始值不大于 value 的最后一段）。"""
    if not bands:
        bands = BADGE_BANDS_DEFAULT
    color = bands[0].get("color", BADGE_INTEGER_COLOR_DEFAULT)
    for band in bands:
        try:
            at = float(band.get("at", 0))
        except (TypeError, ValueError):
            continue
        if value + 1e-9 >= at:
            color = band.get("color", color)
        else:
            break
    return hex_to_rgb(color)


def balance_badge_spec(
    balance: float | None,
    bands=None,
    hundreds_bands=None,
    integer_color: str = BADGE_INTEGER_COLOR_DEFAULT,
    water_unit: int = BADGE_WATER_UNIT_DEFAULT,
) -> tuple[str, tuple, float]:
    """
    根据余额算出托盘徽标的 (文字, 数字颜色, 水位)（纯函数，便于冒烟测试）。

    文字：
        - <100   -> 整数部分，最多两位数字
        - >=100  -> "xH"（379 -> "3H"），超过 999 封顶为 "9H"

    颜色：
        - <100   -> 按零头 0.xx 落入 bands 的某一段；余额为整数时用 integer_color
        - >=100  -> 按绝对金额落入 hundreds_bands 的某一段

    bands / hundreds_bands 形如 [{"at": 0.0, "color": "#FF0000"}, ...]，
    最多 MAX_COLOR_BANDS 段，按 at 升序。

    水位（0~1，自下而上）= 当前格内的填充比例：
        余额每 water_unit 元为一格（默认 1 元）。格内从底面往上灌，
        正好落在格线上时视为满（新格子刚开始，还没消耗）。
        例如单位 1 元时：10.00 -> 满、10.20 -> 20%、9.80 -> 80%、9.00 -> 满。
    """
    if balance is None or balance < 0:
        return "--", BADGE_WHITE, 0.0

    value = round(float(balance), 2)
    unit = max(1, int(water_unit))
    bands = bands or BADGE_BANDS_DEFAULT
    hundreds_bands = hundreds_bands or BADGE_HUNDREDS_BANDS_DEFAULT

    if value >= 100:
        text = f"{min(int(value // 100), 9)}H"
        color = pick_band_color(value, hundreds_bands)
        return text, color, _water_level(value, unit)

    integer = int(value)
    text = str(integer)
    frac = round(value - integer, 2)
    if frac == 0.0:
        color = hex_to_rgb(integer_color, BADGE_WHITE)
    else:
        color = pick_band_color(frac, bands)
    return text, color, _water_level(value, unit)


def _water_level(value: float, unit: int) -> float:
    """格内填充比例；正好落在格线上（余数为 0）时视为满。"""
    unit = max(1, int(unit))
    within = round(value % unit, 4)
    if within == 0.0:
        return 1.0
    return round(within / unit, 4)


def quantize_water_level(level: float, steps: int = WATER_LEVEL_STEPS) -> float:
    """把水位量化到 1/steps，减少托盘重绘次数。"""
    steps = max(1, int(steps))
    level = min(max(float(level), 0.0), 1.0)
    return round(level * steps) / steps


def _fit_badge_font(draw, text: str, max_w: int, max_h: int, start: int):
    """从 start 号字往下找第一个能塞进 (max_w, max_h) 的字体"""
    font = None
    for size in range(start, 7, -1):
        for name in _BADGE_FONTS:
            try:
                font = ImageFont.truetype(name, size)
                break
            except (OSError, IOError):
                continue
        if font is None:
            return ImageFont.load_default()
        bbox = draw.textbbox((0, 0), text, font=font)
        if bbox[2] - bbox[0] <= max_w and bbox[3] - bbox[1] <= max_h:
            return font
    return font if font is not None else ImageFont.load_default()


def create_balance_badge_icon(
    text: str,
    color: tuple,
    level: float = 1.0,
    mode: str = BADGE_DISPLAY_MODE_DEFAULT,
    size: int = 64,
    alert: bool = False,
) -> Image.Image:
    """
    黑底矩形框 + 淡蓝水位 + 指定颜色的余额数字。

    mode: "both"（数字+水位）/ "number"（仅数字）/ "water"（仅水位）
    alert: 为真时在矩形外圈画一圈红色描边，用于闪烁
    """
    if mode not in ("both", "number", "water"):
        mode = "both"
    draw_water = mode in ("both", "water")
    draw_text = mode in ("both", "number")

    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    margin = max(1, size // 16)
    box = (margin, margin, size - margin - 1, size - margin - 1)
    radius = max(2, size // 8)
    if hasattr(draw, "rounded_rectangle"):
        draw.rounded_rectangle(box, radius=radius, fill=BADGE_BG)
    else:  # 兼容很老的 Pillow
        draw.rectangle(box, fill=BADGE_BG)

    # --- 水位：先盖在黑底上，数字最后画，保证不遮挡文字 ---
    level = quantize_water_level(level)
    if draw_water and level > 0.0:
        mask = Image.new("L", (size, size), 0)
        mdraw = ImageDraw.Draw(mask)
        if hasattr(mdraw, "rounded_rectangle"):
            mdraw.rounded_rectangle(box, radius=radius, fill=255)
        else:
            mdraw.rectangle(box, fill=255)
        if level < 1.0:
            water_top = box[3] - (box[3] - box[1]) * level
            mdraw.rectangle((0, 0, size - 1, int(water_top)), fill=0)

        water = Image.new("RGBA", (size, size), BADGE_WATER)
        water.putalpha(mask.point(lambda v: v * BADGE_WATER[3] // 255))
        img.alpha_composite(water)

    # --- 红色描边：画在水位之上、数字之下，闪烁时更醒目 ---
    if alert:
        border = max(2, size // 8)
        draw.rounded_rectangle(
            box, radius=radius, outline=BADGE_ALERT_BORDER, width=border
        )

    if draw_text:
        inner_w = box[2] - box[0]
        inner_h = box[3] - box[1]
        font = _fit_badge_font(draw, text, inner_w - 2, inner_h - 2, inner_h)

        bbox = draw.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text(
            (
                box[0] + (inner_w - tw) / 2 - bbox[0],
                box[1] + (inner_h - th) / 2 - bbox[1],
            ),
            text,
            fill=color,
            font=font,
        )
    return img
