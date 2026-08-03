import pytest

from anchor_item import (
    CATEGORY_UNSPECIFIED,
    AnchorItem,
    AnchorValidationError,
    build_confirmed_anchor,
    confirmed_anchor_for,
    infer_anchor_category,
    infer_anchor_defaults,
    store_confirmed_anchor,
)


COLORS = ["白色", "藏蓝", "米色", "粉色", "灰色", "黑色", "蓝色", "绿色", "卡其色", "棕色"]


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("白色衬衫", "上衣"),
        ("针织衫", "上衣"),
        ("黑色西装", "上衣"),
        ("灰色马甲", "上衣"),
        ("深灰西裤", "裤子"),
        ("宽松牛仔裤", "裤子"),
        ("半裙", "裤子"),
        ("白色运动鞋", "鞋子"),
        ("黑色乐福鞋", "鞋子"),
        ("棕色短靴", "鞋子"),
    ],
)
def test_category_aliases_map_to_three_supported_categories(label, expected):
    assert infer_anchor_category("", [label]) == expected


def test_suit_and_mixed_categories_are_not_forced():
    assert infer_anchor_category("套装", ["黑色西装", "黑色长裤"]) == CATEGORY_UNSPECIFIED
    assert infer_anchor_category("", ["白色衬衫", "深灰西裤"]) == CATEGORY_UNSPECIFIED
    assert infer_anchor_category("配饰", ["围巾"]) == CATEGORY_UNSPECIFIED


def test_inferred_defaults_reuse_existing_color_and_style_normalization():
    defaults = infer_anchor_defaults(
        "上衣",
        [" 黑色西装 "],
        "深灰",
        ["暗黑", "解构正装"],
        COLORS,
    )
    assert defaults == ("黑色西装", "上衣", "灰色", "商务")


def test_user_modified_anchor_values_override_automatic_values():
    anchor = build_confirmed_anchor(
        "image-hash:qwen3.7-flash",
        automatic_name="黑色西装",
        automatic_category="上衣",
        automatic_color="黑色",
        automatic_style="商务",
        selected_name="  我的灰色西裤  ",
        selected_category="裤子",
        selected_color="灰色",
        selected_style="简约",
        available_colors=COLORS,
    )

    assert anchor == AnchorItem(
        cache_key="image-hash:qwen3.7-flash",
        name="我的灰色西裤",
        category="裤子",
        primary_color="灰色",
        style="简约",
    )


@pytest.mark.parametrize(
    ("name", "message"),
    [
        ("   ", "单品名称不能为空"),
        ("长" * 31, "单品名称不能超过30个字符"),
    ],
)
def test_invalid_anchor_names_are_rejected(name, message):
    with pytest.raises(AnchorValidationError, match=message):
        build_confirmed_anchor(
            "image-hash:model",
            automatic_name="上衣",
            automatic_category="上衣",
            automatic_color="黑色",
            automatic_style="商务",
            selected_name=name,
            selected_category="上衣",
            selected_color="黑色",
            selected_style="商务",
            available_colors=COLORS,
        )


def test_anchor_confirmation_is_bound_to_current_cache_key():
    state = {}
    anchor = AnchorItem("first-hash:model", "我的上衣", "上衣", "黑色", "商务")
    store_confirmed_anchor(state, anchor)

    assert confirmed_anchor_for(state, "first-hash:model") == anchor
    assert confirmed_anchor_for(state, "second-hash:model") is None
