"""图片分析标签的确定性标准化与会话偏好绑定。"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, MutableMapping, Sequence
from dataclasses import dataclass
from typing import Any


UNSPECIFIED = "不指定"
REFERENCE_STYLES = ("简约", "休闲", "商务", "运动")
NEUTRAL_COLORS = frozenset({"黑色", "白色", "灰色", "米色", "藏蓝"})
COORDINATING_COLOR_PAIRS = frozenset({
    frozenset(("黑色", "白色")),
    frozenset(("黑色", "灰色")),
    frozenset(("黑色", "米色")),
    frozenset(("黑色", "藏蓝")),
    frozenset(("白色", "灰色")),
    frozenset(("白色", "米色")),
    frozenset(("白色", "藏蓝")),
    frozenset(("灰色", "米色")),
    frozenset(("灰色", "藏蓝")),
    frozenset(("米色", "藏蓝")),
    frozenset(("蓝色", "白色")),
    frozenset(("蓝色", "灰色")),
    frozenset(("蓝色", "米色")),
    frozenset(("蓝色", "藏蓝")),
    frozenset(("粉色", "白色")),
    frozenset(("粉色", "灰色")),
    frozenset(("粉色", "米色")),
    frozenset(("绿色", "米色")),
    frozenset(("绿色", "卡其色")),
    frozenset(("绿色", "棕色")),
    frozenset(("卡其色", "棕色")),
    frozenset(("卡其色", "藏蓝")),
})

_COLOR_ALIASES = {
    "黑": "黑色",
    "黑色": "黑色",
    "灰": "灰色",
    "灰色": "灰色",
    "深灰": "灰色",
    "深灰色": "灰色",
    "炭灰": "灰色",
    "炭灰色": "灰色",
    "银灰": "灰色",
    "银灰色": "灰色",
    "海军蓝": "藏蓝",
    "海军蓝色": "藏蓝",
    "深蓝": "藏蓝",
    "深蓝色": "藏蓝",
    "藏青": "藏蓝",
    "藏青色": "藏蓝",
    "藏蓝": "藏蓝",
    "米白": "米色",
    "米白色": "米色",
    "燕麦": "米色",
    "燕麦色": "米色",
    "奶油": "米色",
    "奶油色": "米色",
    "米色": "米色",
    "白": "白色",
    "白色": "白色",
    "纯白": "白色",
    "纯白色": "白色",
    "粉": "粉色",
    "粉色": "粉色",
    "粉红": "粉色",
    "粉红色": "粉色",
    "雾粉": "粉色",
    "雾粉色": "粉色",
    "蓝": "蓝色",
    "蓝色": "蓝色",
    "浅蓝": "蓝色",
    "浅蓝色": "蓝色",
    "天蓝": "蓝色",
    "天蓝色": "蓝色",
    "绿": "绿色",
    "绿色": "绿色",
    "墨绿": "绿色",
    "墨绿色": "绿色",
    "森林绿": "绿色",
    "森林绿色": "绿色",
    "卡其": "卡其色",
    "卡其色": "卡其色",
    "棕": "棕色",
    "棕色": "棕色",
    "咖啡": "棕色",
    "咖啡色": "棕色",
    "褐": "棕色",
    "褐色": "棕色",
}

_STYLE_ALIASES = {
    "正装": "商务",
    "西装": "商务",
    "商务": "商务",
    "通勤": "商务",
    "解构正装": "商务",
    "极简": "简约",
    "简洁": "简约",
    "基础款": "简约",
    "简约": "简约",
    "日常": "休闲",
    "街头": "休闲",
    "宽松": "休闲",
    "休闲": "休闲",
    "运动": "运动",
    "训练": "运动",
    "户外": "运动",
    "athleisure": "运动",
}


@dataclass(frozen=True)
class ImagePreference:
    """用户确认后的图片偏好；``cache_key`` 将偏好绑定到图片与模型。"""

    cache_key: str
    primary_color: str | None
    style: str | None


def _normalized_label(value: str) -> str:
    return "".join(value.strip().casefold().split())


def normalize_color(value: str, available_colors: Iterable[str]) -> str:
    """将可靠颜色别名映射到商品库颜色，否则返回“不指定”。"""
    allowed = {color.strip() for color in available_colors if color.strip()}
    raw = value.strip()
    if raw in allowed:
        return raw
    mapped = _COLOR_ALIASES.get(_normalized_label(raw))
    return mapped if mapped in allowed else UNSPECIFIED


def normalize_style(values: str | Iterable[str]) -> str:
    """按模型标签顺序选择第一个可靠的四类风格映射。"""
    labels = (values,) if isinstance(values, str) else values
    for label in labels:
        if not isinstance(label, str):
            continue
        mapped = _STYLE_ALIASES.get(_normalized_label(label))
        if mapped is not None:
            return mapped
    return UNSPECIFIED


def colors_coordinate(first: str, second: str) -> bool:
    """返回两个不同颜色是否命中共享的明确协调色规则。"""
    return first != second and frozenset((first, second)) in COORDINATING_COLOR_PAIRS


def is_neutral_coordination(first: str, second: str) -> bool:
    """返回协调色是否属于中性色组合。"""
    return colors_coordinate(first, second) and first in NEUTRAL_COLORS and second in NEUTRAL_COLORS


def infer_preference_defaults(
    primary_color: str,
    style_tags: Iterable[str],
    available_colors: Iterable[str],
) -> tuple[str, str]:
    """从已校验的视觉字段生成可编辑预填值，不直接生成推荐参数。"""
    return (
        normalize_color(primary_color, available_colors),
        normalize_style(style_tags),
    )


def build_confirmed_preference(
    cache_key: str,
    *,
    automatic_color: str,
    automatic_style: str,
    selected_color: str | None,
    selected_style: str | None,
    available_colors: Sequence[str],
) -> ImagePreference:
    """以用户选择优先构造确认偏好，并校验值来自界面允许选项。"""
    color = selected_color if selected_color is not None else automatic_color
    style = selected_style if selected_style is not None else automatic_style
    allowed_colors = {UNSPECIFIED, *available_colors}
    allowed_styles = {UNSPECIFIED, *REFERENCE_STYLES}
    if color not in allowed_colors:
        raise ValueError("参考主色不在商品库选项中")
    if style not in allowed_styles:
        raise ValueError("参考风格不在允许选项中")
    if not cache_key:
        raise ValueError("图片偏好缺少缓存键")
    return ImagePreference(
        cache_key=cache_key,
        primary_color=None if color == UNSPECIFIED else color,
        style=None if style == UNSPECIFIED else style,
    )


def store_confirmed_preference(
    session_state: MutableMapping[str, Any], preference: ImagePreference
) -> None:
    """只保存确认结果；不保存图片或视觉原始响应。"""
    preferences = session_state.setdefault("confirmed_image_preferences", {})
    if not isinstance(preferences, MutableMapping):
        preferences = {}
        session_state["confirmed_image_preferences"] = preferences
    preferences[preference.cache_key] = preference


def confirmed_preference_for(
    session_state: Mapping[str, Any], cache_key: str | None
) -> ImagePreference | None:
    """仅返回与当前图片和模型缓存键完全匹配的确认偏好。"""
    if not cache_key:
        return None
    try:
        preferences = session_state["confirmed_image_preferences"]
    except (KeyError, TypeError):
        preferences = {}
    if not isinstance(preferences, Mapping):
        return None
    preference = preferences.get(cache_key)
    if not isinstance(preference, ImagePreference) or preference.cache_key != cache_key:
        return None
    return preference
