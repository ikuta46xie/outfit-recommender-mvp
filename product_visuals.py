"""将商品 ID 安全映射到仓库内的本地 SVG 示意图。"""

from __future__ import annotations

import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
PRODUCT_ASSET_DIRECTORY = (PROJECT_ROOT / "assets" / "products").resolve()
PLACEHOLDER_PATH = PRODUCT_ASSET_DIRECTORY / "placeholder.svg"
PRODUCT_ID_PATTERN = re.compile(r"^(?:TOP|BOTTOM|SHOES)\d{3}$", re.ASCII)


def placeholder_image_path() -> Path:
    """返回仓库内固定的本地占位图路径。"""
    return PLACEHOLDER_PATH


def product_image_path(product_id: str) -> Path:
    """返回安全商品图片路径；非法或缺失 ID 统一降级为占位图。"""
    if not isinstance(product_id, str) or PRODUCT_ID_PATTERN.fullmatch(product_id) is None:
        return PLACEHOLDER_PATH

    candidate = (PRODUCT_ASSET_DIRECTORY / f"{product_id}.svg").resolve()
    try:
        candidate.relative_to(PRODUCT_ASSET_DIRECTORY)
    except ValueError:
        return PLACEHOLDER_PATH
    return candidate if candidate.is_file() else PLACEHOLDER_PATH
