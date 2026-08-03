"""基于演示商品 CSV 的规则式穿搭推荐器。"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from itertools import product as cartesian_product
from pathlib import Path
from typing import Iterable, Sequence

from image_preferences import ImagePreference, colors_coordinate, is_neutral_coordination


CATEGORIES = ("上衣", "裤子", "鞋子")
REQUIRED_COLUMNS = {"id", "name", "category", "color", "price", "sizes", "scenes", "styles", "data_label"}
MAX_IMAGE_PREFERENCE_BONUS = 3.0


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
    base_score: float
    image_preference_bonus: float = 0.0
    recommendation_reasons: tuple[str, ...] = ()

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


def _image_preference_score(
    items: tuple[Product, Product, Product],
    preference: ImagePreference | None,
) -> tuple[float, tuple[str, ...]]:
    """计算有上限的软加分，并从实际命中规则生成最多两条理由。"""
    if preference is None:
        return 0.0, ()

    bonus = 0.0
    reasons: list[str] = []
    if preference.primary_color is not None:
        exact_items = [item for item in items if item.color == preference.primary_color]
        coordinated_items = [
            item for item in items
            if colors_coordinate(item.color, preference.primary_color)
        ]
        bonus += len(exact_items) * 0.8
        bonus += len(coordinated_items) * 0.35
        if exact_items:
            reasons.append(f"{exact_items[0].name}与图片主色一致")
        if coordinated_items:
            item = coordinated_items[0]
            if is_neutral_coordination(item.color, preference.primary_color):
                reasons.append(f"{item.name}与{preference.primary_color}形成中性色协调")
            else:
                reasons.append(f"{item.name}与{preference.primary_color}形成协调配色")

    if preference.style is not None:
        style_hits = [item for item in items if preference.style in item.styles]
        bonus += len(style_hits) * 0.2
        if style_hits:
            reasons.append(f"本套包含用户确认的{preference.style}风格")

    if not reasons:
        reasons.append("未命中明确图片偏好，本套按基础匹配分排序")
    return min(round(bonus, 3), MAX_IMAGE_PREFERENCE_BONUS), tuple(reasons[:2])


def _base_sort_key(outfit: Outfit) -> tuple[float, int, tuple[str, str, str]]:
    """返回最终排序键：总分降序、总价升序、商品 ID 升序。"""
    return (-outfit.score, outfit.total_price, outfit.product_ids)


def _rerank_for_diversity(candidates: Sequence[Outfit], limit: int) -> list[Outfit]:
    """在不丢弃候选的前提下，贪心选择商品重复最少的搭配。"""
    if not candidates or limit == 0:
        return []

    remaining = list(candidates)
    selected = [remaining.pop(0)]
    used_product_ids = set(selected[0].product_ids)

    while remaining and len(selected) < limit:
        next_index = min(
            range(len(remaining)),
            key=lambda index: (
                len(used_product_ids.intersection(remaining[index].product_ids)),
                _base_sort_key(remaining[index]),
            ),
        )
        chosen = remaining.pop(next_index)
        selected.append(chosen)
        used_product_ids.update(chosen.product_ids)

    return selected


def recommend_outfits(
    csv_path: str | Path, *, budget: int, top_size: str, bottom_size: str,
    scene: str, style: str, excluded_colors: Iterable[str] = (), limit: int = 3,
    image_preference: ImagePreference | None = None,
) -> list[Outfit]:
    """先应用硬约束，再计算基础分与可选图片软加分并进行多样性重排。"""
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
        items = (top, bottom, shoe)
        base_score = _outfit_score(items, budget)
        preference_bonus, reasons = _image_preference_score(items, image_preference)
        candidates.append(Outfit(
            top=top,
            bottom=bottom,
            shoes=shoe,
            total_price=total,
            score=round(base_score + preference_bonus, 3),
            base_score=base_score,
            image_preference_bonus=preference_bonus,
            recommendation_reasons=reasons,
        ))
    candidates.sort(key=_base_sort_key)
    return _rerank_for_diversity(candidates, limit)
