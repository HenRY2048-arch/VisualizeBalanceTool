"""程序化生成托盘图标，支持加载外部自定义图标"""

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

# 配色阈值默认值，与 config._DEFAULTS 保持一致（冒烟测试会校验两者不漂移）
BADGE_GREEN_AT_DEFAULT = 0.50
BADGE_RED_BELOW_DEFAULT = 0.25

# 优先使用加粗字体，缺失时逐个回退
_BADGE_FONTS = ("arialbd.ttf", "arial.ttf", "DejaVuSans-Bold.ttf")


def balance_badge_spec(
    balance: float | None,
    green_at: float = BADGE_GREEN_AT_DEFAULT,
    red_below: float = BADGE_RED_BELOW_DEFAULT,
) -> tuple[str, tuple]:
    """
    根据余额算出托盘徽标要显示的文字与数字颜色（纯函数，便于冒烟测试）。

    文字：余额整数部分，最多两位数字（>=100 时封顶为 "99"）。
    颜色：按小数零头分级，两个阈值可在设置里自定义
        - 无有效余额 / 余额 < 0    -> "--"（白）
        - 零头 == 0（如 20.00）    -> 白
        - 零头 < red_below（如 0.08 < 0.25）-> 红
        - red_below <= 零头 < green_at       -> 橙（如 0.43）
        - 零头 >= green_at（如 0.56 >= 0.50）-> 草绿
    """
    if balance is None or balance < 0:
        return "--", BADGE_WHITE

    value = round(float(balance), 2)
    integer = int(value)
    text = str(integer) if integer < 100 else "99"

    frac = round(value - integer, 2)
    if frac == 0.0:
        color = BADGE_WHITE
    elif frac < red_below:
        color = BADGE_RED
    elif frac < green_at:
        color = BADGE_ORANGE
    else:
        color = BADGE_GREEN
    return text, color


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


def create_balance_badge_icon(text: str, color: tuple, size: int = 64) -> Image.Image:
    """黑底矩形框 + 指定颜色的余额数字（外框尺寸与其它图标一致）"""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    margin = max(1, size // 16)
    box = (margin, margin, size - margin - 1, size - margin - 1)
    radius = max(2, size // 8)
    if hasattr(draw, "rounded_rectangle"):
        draw.rounded_rectangle(box, radius=radius, fill=BADGE_BG)
    else:  # 兼容很老的 Pillow
        draw.rectangle(box, fill=BADGE_BG)

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
