from pathlib import Path

import pytest

from image_preferences import ImagePreference
from recommender import MAX_IMAGE_PREFERENCE_BONUS, load_products, recommend_outfits


DATA_PATH = Path(__file__).parents[1] / "data" / "products.csv"


@pytest.fixture
def recommendations():
    return recommend_outfits(DATA_PATH, budget=1200, top_size="M", bottom_size="M",
                             scene="通勤", style="简约", limit=3)


def test_budget_limit(recommendations):
    assert recommendations
    assert all(outfit.total_price <= 1200 for outfit in recommendations)


def test_default_conditions_return_three_outfits(recommendations):
    assert len(recommendations) == 3


def test_size_matching(recommendations):
    assert all("M" in outfit.top.sizes for outfit in recommendations)
    assert all("M" in outfit.bottom.sizes for outfit in recommendations)


def test_excluded_color_is_not_used():
    outfits = recommend_outfits(DATA_PATH, budget=1400, top_size="M", bottom_size="M",
        scene="通勤", style="简约", excluded_colors=["黑色", "白色"])
    assert outfits
    assert all(item.color not in {"黑色", "白色"} for outfit in outfits
               for item in (outfit.top, outfit.bottom, outfit.shoes))


def test_all_products_come_from_csv(recommendations):
    source_ids = {product.id for product in load_products(DATA_PATH)}
    recommended_ids = {item.id for outfit in recommendations
                       for item in (outfit.top, outfit.bottom, outfit.shoes)}
    assert recommended_ids <= source_ids


def test_outfits_are_unique(recommendations):
    signatures = [outfit.product_ids for outfit in recommendations]
    assert len(signatures) == len(set(signatures))


def test_default_results_do_not_repeat_items_by_category(recommendations):
    assert len({outfit.top.id for outfit in recommendations}) == 3
    assert len({outfit.bottom.id for outfit in recommendations}) == 3
    assert len({outfit.shoes.id for outfit in recommendations}) == 3


def test_limited_candidates_reuse_items_and_still_fill_limit(tmp_path):
    csv_path = tmp_path / "limited-products.csv"
    csv_path.write_text(
        """id,name,category,color,price,sizes,scenes,styles,data_label
TOP001,唯一上衣,上衣,白色,100,M,通勤,简约,演示数据（非真实库存）
BOTTOM001,裤子一,裤子,黑色,100,M,通勤,简约,演示数据（非真实库存）
BOTTOM002,裤子二,裤子,灰色,110,M,通勤,简约,演示数据（非真实库存）
SHOES001,鞋子一,鞋子,白色,100,40,通勤,简约,演示数据（非真实库存）
SHOES002,鞋子二,鞋子,黑色,110,40,通勤,简约,演示数据（非真实库存）
""",
        encoding="utf-8",
    )

    outfits = recommend_outfits(
        csv_path,
        budget=500,
        top_size="M",
        bottom_size="M",
        scene="通勤",
        style="简约",
        limit=3,
    )

    assert len(outfits) == 3
    assert len({outfit.top.id for outfit in outfits}) == 1
    assert len({outfit.product_ids for outfit in outfits}) == 3


def test_demo_catalog_has_24_balanced_products():
    products = load_products(DATA_PATH)
    assert len(products) == 24
    assert all(product.data_label == "演示数据（非真实库存）" for product in products)
    counts = {category: sum(item.category == category for item in products)
              for category in ("上衣", "裤子", "鞋子")}
    assert counts == {"上衣": 8, "裤子": 8, "鞋子": 8}


def test_normal_mode_keeps_v03_default_order_and_scores(recommendations):
    assert [outfit.product_ids for outfit in recommendations] == [
        ("TOP006", "BOTTOM007", "SHOES002"),
        ("TOP002", "BOTTOM001", "SHOES007"),
        ("TOP001", "BOTTOM004", "SHOES001"),
    ]
    assert [outfit.score for outfit in recommendations] == [16.963, 16.054, 15.696]
    assert all(outfit.score == outfit.base_score for outfit in recommendations)
    assert all(outfit.image_preference_bonus == 0 for outfit in recommendations)
    assert all(not outfit.recommendation_reasons for outfit in recommendations)


def test_black_business_preference_adds_a_bounded_soft_score():
    preference = ImagePreference("image-hash:qwen3.7-flash", "黑色", "商务")
    outfits = recommend_outfits(
        DATA_PATH,
        budget=1400,
        top_size="M",
        bottom_size="M",
        scene="通勤",
        style="商务",
        image_preference=preference,
    )

    assert outfits
    assert all(0 < outfit.image_preference_bonus <= MAX_IMAGE_PREFERENCE_BONUS for outfit in outfits)
    assert all(outfit.score == pytest.approx(outfit.base_score + outfit.image_preference_bonus)
               for outfit in outfits)


def test_image_guided_results_are_reproducible():
    preference = ImagePreference("image-hash:qwen3.7-flash", "黑色", "商务")
    arguments = dict(
        budget=1400,
        top_size="M",
        bottom_size="M",
        scene="通勤",
        style="商务",
        image_preference=preference,
    )
    first = recommend_outfits(DATA_PATH, **arguments)
    second = recommend_outfits(DATA_PATH, **arguments)

    assert first == second


def test_v04_image_guided_order_and_scores_remain_unchanged():
    preference = ImagePreference("image-hash:qwen3.7-flash", "黑色", "商务")
    outfits = recommend_outfits(
        DATA_PATH,
        budget=1400,
        top_size="M",
        bottom_size="M",
        scene="通勤",
        style="商务",
        image_preference=preference,
    )

    assert [outfit.product_ids for outfit in outfits] == [
        ("TOP006", "BOTTOM007", "SHOES002"),
        ("TOP002", "BOTTOM002", "SHOES004"),
        ("TOP001", "BOTTOM001", "SHOES002"),
    ]
    assert [outfit.score for outfit in outfits] == [18.818, 17.046, 17.225]
    assert [outfit.image_preference_bonus for outfit in outfits] == [2.55, 2.1, 2.1]


def test_image_preference_does_not_bypass_any_hard_filter():
    preference = ImagePreference("image-hash:qwen3.7-flash", "黑色", "商务")
    outfits = recommend_outfits(
        DATA_PATH,
        budget=1100,
        top_size="M",
        bottom_size="L",
        scene="通勤",
        style="简约",
        excluded_colors=["黑色"],
        image_preference=preference,
    )
    source_ids = {product.id for product in load_products(DATA_PATH)}

    assert outfits
    for outfit in outfits:
        assert outfit.total_price <= 1100
        assert "M" in outfit.top.sizes
        assert "L" in outfit.bottom.sizes
        for item in (outfit.top, outfit.bottom, outfit.shoes):
            assert "通勤" in item.scenes
            assert "简约" in item.styles
            assert item.color != "黑色"
            assert item.id in source_ids


def test_recommendation_reasons_match_actual_color_or_style_hits():
    preference = ImagePreference("image-hash:qwen3.7-flash", "黑色", "商务")
    outfits = recommend_outfits(
        DATA_PATH,
        budget=1400,
        top_size="M",
        bottom_size="M",
        scene="通勤",
        style="商务",
        image_preference=preference,
    )

    for outfit in outfits:
        items = (outfit.top, outfit.bottom, outfit.shoes)
        assert 1 <= len(outfit.recommendation_reasons) <= 2
        for reason in outfit.recommendation_reasons:
            if "与图片主色一致" in reason:
                assert any(item.name in reason and item.color == "黑色" for item in items)
            elif "用户确认的商务风格" in reason:
                assert any("商务" in item.styles for item in items)
            else:
                assert "与黑色形成" in reason
