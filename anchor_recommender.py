"""围绕用户自有锚点单品，从 CSV 补齐另外两个类别。"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product as cartesian_product
from pathlib import Path
from typing import Iterable, Sequence

from anchor_item import ANCHOR_CATEGORIES, AnchorItem
from image_preferences import colors_coordinate, is_neutral_coordination
from recommender import CATEGORIES, Product, load_products


MAX_ANCHOR_MATCH_BONUS = 2.0


@dataclass(frozen=True)
class AnchoredOutfit:
    """一个自有锚点与两个真实 CSV 商品组成的补全结果。"""

    anchor: AnchorItem
    purchased_items: tuple[Product, Product]
    total_price: int
    base_score: float
    anchor_match_bonus: float
    score: float
    recommendation_reasons: tuple[str, ...]

    @property
    def product_ids(self) -> tuple[str, str]:
        return tuple(item.id for item in self.purchased_items)

    @property
    def purchased_categories(self) -> tuple[str, str]:
        return tuple(item.category for item in self.purchased_items)

    def item_for_category(self, category: str) -> AnchorItem | Product:
        if category == self.anchor.category:
            return self.anchor
        for item in self.purchased_items:
            if item.category == category:
                return item
        raise KeyError(category)


def _filter_products(
    products: Sequence[Product],
    *,
    category: str,
    size: str,
    scene: str,
    style: str,
    excluded_colors: set[str],
) -> list[Product]:
    return [
        item for item in products
        if item.category == category
        and size in item.sizes
        and scene in item.scenes
        and style in item.styles
        and item.color.casefold() not in excluded_colors
    ]


def _base_score(items: tuple[Product, Product], budget: int) -> float:
    total = sum(item.price for item in items)
    distinct_colors = len({item.color for item in items})
    color_score = {1: 0.5, 2: 1.5}[distinct_colors]
    richness = sum(len(item.scenes) + len(item.styles) for item in items) * 0.05
    return round(10 + total / budget * 5 + color_score + richness, 3)


def _anchor_match_score(
    items: tuple[Product, Product], anchor: AnchorItem
) -> tuple[float, tuple[str, ...]]:
    bonus = 0.0
    reasons: list[str] = []

    if anchor.primary_color is not None:
        exact_items = [item for item in items if item.color == anchor.primary_color]
        coordinated_items = [
            item for item in items
            if colors_coordinate(item.color, anchor.primary_color)
        ]
        bonus += len(exact_items) * 0.8
        bonus += len(coordinated_items) * 0.35
        if exact_items:
            reasons.append(f"{exact_items[0].name}与自有单品主色一致")
        if coordinated_items:
            item = coordinated_items[0]
            if is_neutral_coordination(item.color, anchor.primary_color):
                reasons.append(
                    f"{item.name}与{anchor.primary_color}自有单品形成中性色协调"
                )
            else:
                reasons.append(f"{item.name}与{anchor.primary_color}自有单品形成协调配色")

    if anchor.style is not None:
        style_hits = [item for item in items if anchor.style in item.styles]
        bonus += len(style_hits) * 0.2
        if style_hits:
            reasons.append(f"推荐单品包含与自有单品一致的{anchor.style}风格")

    if not reasons:
        reasons.append("未命中明确锚点偏好，本套按基础条件排序")
    return min(round(bonus, 3), MAX_ANCHOR_MATCH_BONUS), tuple(reasons[:2])


def _sort_key(outfit: AnchoredOutfit) -> tuple[float, int, tuple[str, str]]:
    return (-outfit.score, outfit.total_price, outfit.product_ids)


def _rerank_for_diversity(
    candidates: Sequence[AnchoredOutfit], limit: int
) -> list[AnchoredOutfit]:
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
                _sort_key(remaining[index]),
            ),
        )
        chosen = remaining.pop(next_index)
        selected.append(chosen)
        used_product_ids.update(chosen.product_ids)
    return selected


def recommend_anchor_outfits(
    csv_path: str | Path,
    *,
    anchor: AnchorItem,
    budget: int,
    top_size: str,
    bottom_size: str,
    shoe_size: str,
    scene: str,
    style: str,
    excluded_colors: Iterable[str] = (),
    limit: int = 3,
) -> list[AnchoredOutfit]:
    """应用购买商品硬约束，补齐锚点之外的两个类别。"""
    if anchor.category not in ANCHOR_CATEGORIES:
        raise ValueError("锚点类别无效")
    if budget <= 0:
        raise ValueError("预算必须大于 0")
    if limit < 0:
        raise ValueError("limit 不能小于 0")
    if limit == 0:
        return []

    products = load_products(csv_path)
    excluded = {color.strip().casefold() for color in excluded_colors if color.strip()}
    size_by_category = {"上衣": top_size, "裤子": bottom_size, "鞋子": shoe_size}
    missing_categories = tuple(
        category for category in CATEGORIES if category != anchor.category
    )
    pools = [
        _filter_products(
            products,
            category=category,
            size=size_by_category[category],
            scene=scene,
            style=style,
            excluded_colors=excluded,
        )
        for category in missing_categories
    ]

    candidates: list[AnchoredOutfit] = []
    seen: set[tuple[str, str]] = set()
    for first, second in cartesian_product(*pools):
        items = (first, second)
        product_ids = (first.id, second.id)
        total_price = first.price + second.price
        if total_price > budget or product_ids in seen:
            continue
        seen.add(product_ids)
        base_score = _base_score(items, budget)
        anchor_bonus, reasons = _anchor_match_score(items, anchor)
        candidates.append(AnchoredOutfit(
            anchor=anchor,
            purchased_items=items,
            total_price=total_price,
            base_score=base_score,
            anchor_match_bonus=anchor_bonus,
            score=round(base_score + anchor_bonus, 3),
            recommendation_reasons=reasons,
        ))

    candidates.sort(key=_sort_key)
    return _rerank_for_diversity(candidates, limit)
