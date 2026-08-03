import pytest

from image_preferences import (
    UNSPECIFIED,
    ImagePreference,
    build_confirmed_preference,
    confirmed_preference_for,
    infer_preference_defaults,
    normalize_color,
    normalize_style,
    store_confirmed_preference,
)


COLORS = ["白色", "藏蓝", "米色", "粉色", "灰色", "黑色", "蓝色", "绿色", "卡其色", "棕色"]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("黑", "黑色"),
        ("深灰", "灰色"),
        ("炭灰", "灰色"),
        ("海军蓝", "藏蓝"),
        ("深蓝色", "藏蓝"),
        ("藏青", "藏蓝"),
        ("米白", "米色"),
        ("燕麦色", "米色"),
        ("奶油色", "米色"),
        ("雾粉", "粉色"),
        ("森林绿", "绿色"),
        ("咖啡色", "棕色"),
    ],
)
def test_color_aliases_map_to_catalog_colors(raw, expected):
    assert normalize_color(raw, COLORS) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("解构正装", "商务"),
        ("西装", "商务"),
        ("极简", "简约"),
        ("基础款", "简约"),
        ("街头", "休闲"),
        ("宽松", "休闲"),
        ("训练", "运动"),
        ("Athleisure", "运动"),
    ],
)
def test_style_aliases_are_deterministic(raw, expected):
    assert normalize_style(raw) == expected


def test_unreliable_style_is_not_forced_into_supported_styles():
    assert normalize_style(["暗黑", "前卫"]) == UNSPECIFIED
    assert normalize_color("彩虹渐变", COLORS) == UNSPECIFIED


def test_inference_skips_unreliable_label_and_uses_next_reliable_label():
    assert infer_preference_defaults("深灰", ["暗黑", "通勤"], COLORS) == ("灰色", "商务")


def test_user_modified_values_override_automatic_defaults():
    preference = build_confirmed_preference(
        "hash:model",
        automatic_color="黑色",
        automatic_style="商务",
        selected_color="米色",
        selected_style="休闲",
        available_colors=COLORS,
    )

    assert preference == ImagePreference(
        cache_key="hash:model",
        primary_color="米色",
        style="休闲",
    )


def test_explicit_unspecified_overrides_automatic_defaults():
    preference = build_confirmed_preference(
        "hash:model",
        automatic_color="黑色",
        automatic_style="商务",
        selected_color=UNSPECIFIED,
        selected_style=UNSPECIFIED,
        available_colors=COLORS,
    )
    assert preference.primary_color is None
    assert preference.style is None


def test_confirmed_preference_is_bound_to_current_image_cache_key():
    state = {}
    first = ImagePreference("first-hash:model", "黑色", "商务")
    store_confirmed_preference(state, first)

    assert confirmed_preference_for(state, "first-hash:model") == first
    assert confirmed_preference_for(state, "second-hash:model") is None
