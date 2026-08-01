"""基于演示商品 CSV 的规则式穿搭推荐器。"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from itertools import product as cartesian_product
from pathlib import Path
from typing import Iterable, Sequence


CATEGORIES = ("上衣", "裤子", "鞋子")
REQUIRED_COLUMNS = {"id", "name", "category", "color", "price", "sizes", "scenes", "styles", "data_label"}


@dataclass(frozen=True)
class Product:
    id: str
    name: str
    category: str
    color: str
    price: int
    sizes: tuple[str, ...]
    scenes: tuple[str, ...]
    styles: tuple[str, ...]
    data_label: str


@dataclass(frozen=True)
class Outfit:
    top: Product
    bottom: Product
    shoes: Product
    total_price: int
    score: float

    @property
    def product_ids(self) -> tuple[str, str, str]:
        return (self.top.id, self.bottom.id, self.shoes.id)


def _split_tags(value: str) -> tuple[str, ...]:
    return tuple(tag.strip() for tag in value.split("|") if tag.strip())


def load_products(csv_path: str | Path) -> list[Product]:
    """读取并校验商品 CSV。"""
    with Path(csv_path).open("r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        missing = REQUIRED_COLUMNS.difference(reader.fieldnames or [])
        if missing:
            raise ValueError(f"商品 CSV 缺少字段：{', '.join(sorted(missing))}")
        products: list[Product] = []
        seen_ids: set[str] = set()
        for line_number, row in enumerate(reader, start=2):
            product_id = row["id"].strip()
            if not product_id or product_id in seen_ids:
                raise ValueError(f"商品 CSV 第 {line_number} 行的 id 为空或重复")
            if row["category"].strip() not in CATEGORIES:
                raise ValueError(f"商品 CSV 第 {line_number} 行的 category 无效")
            try:
                price = int(row["price"])
            except ValueError as exc:
                raise ValueError(f"商品 CSV 第 {line_number} 行的 price 必须是整数") from exc
            if price <= 0:
                raise ValueError(f"商品 CSV 第 {line_number} 行的 price 必须大于 0")
            seen_ids.add(product_id)
            products.append(Product(
                id=product_id, name=row["name"].strip(), category=row["category"].strip(),
                color=row["color"].strip(), price=price, sizes=_split_tags(row["sizes"]),
                scenes=_split_tags(row["scenes"]), styles=_split_tags(row["styles"]),
                data_label=row["data_label"].strip(),
            ))
    return products


def _filter_products(
    products: Sequence[Product], *, category: str, size: str | None,
    scene: str, style: str, excluded_colors: set[str],
) -> list[Product]:
    return [item for item in products if item.category == category
            and item.color.casefold() not in excluded_colors
            and scene in item.scenes and style in item.styles
            and (size is None or size in item.sizes)]


def _outfit_score(items: tuple[Product, Product, Product], budget: int) -> float:
    total = sum(item.price for item in items)
    distinct_colors = len({item.color for item in items})
    return round(10 + total / budget * 5 + {1: 0.5, 2: 1.5, 3: 1.0}[distinct_colors]
                 + sum(len(item.scenes) + len(item.styles) for item in items) * 0.05, 3)


def recommend_outfits(
    csv_path: str | Path, *, budget: int, top_size: str, bottom_size: str,
    scene: str, style: str, excluded_colors: Iterable[str] = (), limit: int = 3,
) -> list[Outfit]:
    """应用硬性筛选条件，为合法组合打分并返回最多 ``limit`` 套。"""
    if budget <= 0:
        raise ValueError("预算必须大于 0")
    if limit < 0:
        raise ValueError("limit 不能小于 0")
    if limit == 0:
        return []

    products = load_products(csv_path)
    excluded = {color.strip().casefold() for color in excluded_colors if color.strip()}
    common = {"scene": scene, "style": style, "excluded_colors": excluded}
    tops = _filter_products(products, category="上衣", size=top_size, **common)
    bottoms = _filter_products(products, category="裤子", size=bottom_size, **common)
    shoes = _filter_products(products, category="鞋子", size=None, **common)

    candidates: list[Outfit] = []
    seen: set[tuple[str, str, str]] = set()
    for top, bottom, shoe in cartesian_product(tops, bottoms, shoes):
        ids = (top.id, bottom.id, shoe.id)
        total = top.price + bottom.price + shoe.price
        if total > budget or ids in seen:
            continue
        seen.add(ids)
        candidates.append(Outfit(top, bottom, shoe, total, _outfit_score((top, bottom, shoe), budget)))
    candidates.sort(key=lambda outfit: (-outfit.score, outfit.total_price, outfit.product_ids))
    return candidates[:limit]
