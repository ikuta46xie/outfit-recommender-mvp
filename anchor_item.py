"""自有锚点单品的确定性标准化、确认校验与会话绑定。"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, MutableMapping, Sequence
from dataclasses import dataclass
from typing import Any

from image_preferences import (
    REFERENCE_STYLES,
    UNSPECIFIED,
    normalize_color,
    normalize_style,
)


ANCHOR_CATEGORIES = ("上衣", "裤子", "鞋子")
CATEGORY_UNSPECIFIED = "请选择"
MAX_ANCHOR_NAME_LENGTH = 30

_CATEGORY_TERMS = {
    "上衣": (
        "上衣", "衬衫", "t恤", "针织衫", "毛衣", "卫衣", "西装",
        "夹克", "外套", "大衣", "马甲", "背心",
    ),
    "裤子": (
        "裤子", "西装裤", "西裤", "牛仔裤", "休闲裤", "运动裤",
        "长裤", "短裤", "半裙", "裙子", "裤",
    ),
    "鞋子": (
        "鞋子", "运动鞋", "板鞋", "皮鞋", "乐福鞋", "靴子", "短靴", "鞋",
    ),
}


class AnchorValidationError(ValueError):
    """可安全展示给用户的锚点确认错误。"""

    def __init__(self, user_message: str) -> None:
        super().__init__(user_message)
        self.user_message = user_message


@dataclass(frozen=True)
class AnchorItem:
    """用户确认的自有单品；不含商品 ID、价格、库存或尺码。"""

    cache_key: str
    name: str
    category: str
    primary_color: str | None
    style: str | None


def _normalized_label(value: str) -> str:
    return "".join(value.strip().casefold().split())


def _categories_in_label(value: str) -> set[str]:
    normalized = _normalized_label(value)
    if not normalized:
        return set()
    if "套装" in normalized:
        return set(ANCHOR_CATEGORIES)

    matches: list[tuple[int, str]] = []
    for category, terms in _CATEGORY_TERMS.items():
        for term in terms:
            normalized_term = _normalized_label(term)
            if normalized_term in normalized:
                matches.append((len(normalized_term), category))
    if not matches:
        return set()
    longest = max(length for length, _ in matches)
    return {category for length, category in matches if length == longest}


def infer_anchor_category(category: str, items: Iterable[str]) -> str:
    """结合视觉类别和单品名称预填；套装、混合类别或未知时不强制判断。"""
    labels = [category, *items]
    detected: set[str] = set()
    for label in labels:
        if isinstance(label, str):
            detected.update(_categories_in_label(label))
    return detected.pop() if len(detected) == 1 else CATEGORY_UNSPECIFIED


def infer_anchor_defaults(
    category: str,
    items: Iterable[str],
    primary_color: str,
    style_tags: Iterable[str],
    available_colors: Iterable[str],
) -> tuple[str, str, str, str]:
    """生成可编辑预填值；不会创建已确认锚点。"""
    item_list = [item.strip() for item in items if isinstance(item, str) and item.strip()]
    name = item_list[0][:MAX_ANCHOR_NAME_LENGTH] if item_list else ""
    return (
        name,
        infer_anchor_category(category, item_list),
        normalize_color(primary_color, available_colors),
        normalize_style(style_tags),
    )


def build_confirmed_anchor(
    cache_key: str,
    *,
    automatic_name: str,
    automatic_category: str,
    automatic_color: str,
    automatic_style: str,
    selected_name: str | None,
    selected_category: str | None,
    selected_color: str | None,
    selected_style: str | None,
    available_colors: Sequence[str],
) -> AnchorItem:
    """以用户输入优先构造锚点，并验证所有界面约束。"""
    name_value = selected_name if selected_name is not None else automatic_name
    category_value = selected_category if selected_category is not None else automatic_category
    color_value = selected_color if selected_color is not None else automatic_color
    style_value = selected_style if selected_style is not None else automatic_style

    if not isinstance(name_value, str) or not name_value.strip():
        raise AnchorValidationError("单品名称不能为空。")
    name = name_value.strip()
    if len(name) > MAX_ANCHOR_NAME_LENGTH:
        raise AnchorValidationError("单品名称不能超过30个字符。")
    if category_value not in ANCHOR_CATEGORIES:
        raise AnchorValidationError("请选择单品类别。")
    if color_value not in {UNSPECIFIED, *available_colors}:
        raise AnchorValidationError("单品主色不在商品库选项中。")
    if style_value not in {UNSPECIFIED, *REFERENCE_STYLES}:
        raise AnchorValidationError("单品风格不在允许选项中。")
    if not cache_key:
        raise AnchorValidationError("锚点单品缺少图片缓存键。")

    return AnchorItem(
        cache_key=cache_key,
        name=name,
        category=category_value,
        primary_color=None if color_value == UNSPECIFIED else color_value,
        style=None if style_value == UNSPECIFIED else style_value,
    )


def store_confirmed_anchor(
    session_state: MutableMapping[str, Any], anchor: AnchorItem
) -> None:
    """仅保存确认后的结构化锚点，不保存图片或视觉原始结果。"""
    anchors = session_state.setdefault("confirmed_anchor_items", {})
    if not isinstance(anchors, MutableMapping):
        anchors = {}
        session_state["confirmed_anchor_items"] = anchors
    anchors[anchor.cache_key] = anchor


def confirmed_anchor_for(
    session_state: Mapping[str, Any], cache_key: str | None
) -> AnchorItem | None:
    """仅返回与当前图片和模型缓存键完全一致的锚点。"""
    if not cache_key:
        return None
    try:
        anchors = session_state["confirmed_anchor_items"]
    except (KeyError, TypeError):
        anchors = {}
    if not isinstance(anchors, Mapping):
        return None
    anchor = anchors.get(cache_key)
    if not isinstance(anchor, AnchorItem) or anchor.cache_key != cache_key:
        return None
    return anchor
