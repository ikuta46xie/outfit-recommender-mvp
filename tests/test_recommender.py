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


def test_demo_catalog_has_24_balanced_products():
    products = load_products(DATA_PATH)
    assert len(products) == 24
    assert all(product.data_label == "演示数据（非真实库存）" for product in products)
    counts = {category: sum(item.category == category for item in products)
              for category in ("上衣", "裤子", "鞋子")}
    assert counts == {"上衣": 8, "裤子": 8, "鞋子": 8}
