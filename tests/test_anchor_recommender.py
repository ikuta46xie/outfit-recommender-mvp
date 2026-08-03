from pathlib import Path

import pytest

from anchor_item import AnchorItem
from anchor_recommender import MAX_ANCHOR_MATCH_BONUS, recommend_anchor_outfits
from recommender import Product, load_products


DATA_PATH = Path(__file__).parents[1] / "data" / "products.csv"
COMMON = {
    "budget": 1200,
    "top_size": "M",
    "bottom_size": "M",
    "shoe_size": "40",
    "scene": "通勤",
    "style": "简约",
    "limit": 3,
}


def make_anchor(category="上衣", color="黑色", style="商务"):
    return AnchorItem(
        cache_key="image-hash:qwen3.7-flash",
        name=f"我的{category}",
        category=category,
        primary_color=color,
        style=style,
    )


@pytest.mark.parametrize(
    ("anchor_category", "expected_categories"),
    [
        ("上衣", ("裤子", "鞋子")),
        ("裤子", ("上衣", "鞋子")),
        ("鞋子", ("上衣", "裤子")),
    ],
)
def test_anchor_only_completes_the_two_missing_categories(anchor_category, expected_categories):
    outfits = recommend_anchor_outfits(
        DATA_PATH,
        anchor=make_anchor(anchor_category),
        **COMMON,
    )

    assert len(outfits) == 3
    assert all(outfit.purchased_categories == expected_categories for outfit in outfits)
    assert all(outfit.anchor.category not in outfit.purchased_categories for outfit in outfits)


def test_anchor_is_not_faked_as_a_catalog_product_and_has_no_price():
    anchor = make_anchor("上衣")
    outfit = recommend_anchor_outfits(DATA_PATH, anchor=anchor, **COMMON)[0]

    assert outfit.anchor is anchor
    assert not isinstance(outfit.anchor, Product)
    assert not hasattr(outfit.anchor, "price")
    assert not hasattr(outfit.anchor, "id")


def test_completion_price_only_sums_two_catalog_products_and_respects_budget():
    outfits = recommend_anchor_outfits(DATA_PATH, anchor=make_anchor("裤子"), **COMMON)

    assert outfits
    for outfit in outfits:
        assert outfit.total_price == sum(item.price for item in outfit.purchased_items)
        assert outfit.total_price <= COMMON["budget"]


@pytest.mark.parametrize("anchor_category", ["上衣", "裤子"])
def test_recommended_shoes_use_selected_shoe_size(anchor_category):
    outfits = recommend_anchor_outfits(
        DATA_PATH,
        anchor=make_anchor(anchor_category),
        **{**COMMON, "shoe_size": "44"},
    )
    shoes = [item for outfit in outfits for item in outfit.purchased_items if item.category == "鞋子"]
    assert shoes and all("44" in shoe.sizes for shoe in shoes)


def test_top_and_bottom_sizes_apply_only_when_those_categories_are_purchased():
    pants_anchor = recommend_anchor_outfits(
        DATA_PATH,
        anchor=make_anchor("裤子"),
        **{**COMMON, "top_size": "S"},
    )
    shoe_anchor = recommend_anchor_outfits(
        DATA_PATH,
        anchor=make_anchor("鞋子"),
        **{**COMMON, "top_size": "S", "bottom_size": "L", "shoe_size": "999"},
    )

    assert pants_anchor
    assert all("S" in outfit.item_for_category("上衣").sizes for outfit in pants_anchor)
    assert shoe_anchor
    assert all("S" in outfit.item_for_category("上衣").sizes for outfit in shoe_anchor)
    assert all("L" in outfit.item_for_category("裤子").sizes for outfit in shoe_anchor)


def test_scene_style_and_excluded_colors_remain_hard_constraints():
    outfits = recommend_anchor_outfits(
        DATA_PATH,
        anchor=make_anchor("上衣"),
        budget=1000,
        top_size="M",
        bottom_size="L",
        shoe_size="40",
        scene="通勤",
        style="简约",
        excluded_colors=["黑色"],
    )

    assert outfits
    for outfit in outfits:
        assert outfit.total_price <= 1000
        for item in outfit.purchased_items:
            assert "通勤" in item.scenes
            assert "简约" in item.styles
            assert item.color != "黑色"


def test_every_recommended_item_comes_from_csv():
    source_ids = {product.id for product in load_products(DATA_PATH)}
    outfits = recommend_anchor_outfits(DATA_PATH, anchor=make_anchor("鞋子"), **COMMON)
    assert {item.id for outfit in outfits for item in outfit.purchased_items} <= source_ids


def test_black_business_anchor_has_nonzero_bounded_bonus():
    outfits = recommend_anchor_outfits(DATA_PATH, anchor=make_anchor(), **COMMON)

    assert outfits
    assert all(0 < outfit.anchor_match_bonus <= MAX_ANCHOR_MATCH_BONUS for outfit in outfits)
    assert all(outfit.score == pytest.approx(outfit.base_score + outfit.anchor_match_bonus)
               for outfit in outfits)


def test_reasons_come_from_actual_anchor_matches():
    anchor = make_anchor()
    outfits = recommend_anchor_outfits(DATA_PATH, anchor=anchor, **COMMON)

    for outfit in outfits:
        assert 1 <= len(outfit.recommendation_reasons) <= 2
        for reason in outfit.recommendation_reasons:
            if "与自有单品主色一致" in reason:
                assert any(item.name in reason and item.color == anchor.primary_color
                           for item in outfit.purchased_items)
            elif "一致的商务风格" in reason:
                assert any("商务" in item.styles for item in outfit.purchased_items)
            else:
                assert "与黑色自有单品形成" in reason


def test_no_match_uses_required_fallback_reason():
    outfits = recommend_anchor_outfits(
        DATA_PATH,
        anchor=make_anchor("上衣", color="棕色", style="运动"),
        budget=1400,
        top_size="M",
        bottom_size="M",
        shoe_size="40",
        scene="通勤",
        style="商务",
        limit=3,
    )
    fallback = "未命中明确锚点偏好，本套按基础条件排序"
    assert outfits
    assert any(outfit.recommendation_reasons == (fallback,) for outfit in outfits)


def test_anchor_results_are_reproducible_and_diverse():
    first = recommend_anchor_outfits(DATA_PATH, anchor=make_anchor("上衣"), **COMMON)
    second = recommend_anchor_outfits(DATA_PATH, anchor=make_anchor("上衣"), **COMMON)

    assert first == second
    assert len({outfit.item_for_category("裤子").id for outfit in first}) == 3
    assert len({outfit.item_for_category("鞋子").id for outfit in first}) == 3
