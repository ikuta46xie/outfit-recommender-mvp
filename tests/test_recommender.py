from pathlib import Path

import pytest

from recommender import load_products, recommend_outfits


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
