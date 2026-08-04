"""根据演示商品 CSV 确定性生成本地 SVG 商品示意图。"""

from __future__ import annotations

import csv
import re
from pathlib import Path
from xml.sax.saxutils import escape


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = PROJECT_ROOT / "data" / "products.csv"
ASSET_DIRECTORY = PROJECT_ROOT / "assets" / "products"
PLACEHOLDER_FILENAME = "placeholder.svg"
PRODUCT_ID_PATTERN = re.compile(r"^(TOP|BOTTOM|SHOES)\d{3}$", re.ASCII)

CATEGORY_METADATA = {
    "上衣": ("TOP", "top"),
    "裤子": ("BOTTOM", "bottom"),
    "鞋子": ("SHOES", "shoes"),
}

COLOR_PALETTE = {
    "白色": "#FFFFFF",
    "藏蓝": "#243B5A",
    "米色": "#D8C7A3",
    "粉色": "#E7A8B8",
    "灰色": "#78838E",
    "黑色": "#202124",
    "蓝色": "#6EA6D8",
    "绿色": "#567A5B",
    "卡其色": "#B59A69",
    "棕色": "#7B5035",
}

BACKGROUND_COLOR = "#F3F5F8"
CARD_COLOR = "#FFFFFF"
OUTLINE_COLOR = "#566273"
DETAIL_COLOR = "#94A0AE"
LABEL_COLOR = "#E7EBF0"
TEXT_COLOR = "#364152"


def _top_silhouette(fill: str) -> str:
    return f"""
  <g data-silhouette="top" stroke-linecap="round" stroke-linejoin="round">
    <path d="M111 73 L81 91 L48 142 L76 161 L96 132 L96 266 L224 266 L224 132 L244 161 L272 142 L239 91 L209 73 L184 94 Q160 111 136 94 Z" fill="{fill}" stroke="{OUTLINE_COLOR}" stroke-width="5"/>
    <path d="M136 94 Q160 122 184 94" fill="none" stroke="{DETAIL_COLOR}" stroke-width="4"/>
    <path d="M113 169 H207" fill="none" stroke="{DETAIL_COLOR}" stroke-width="3" opacity="0.7"/>
  </g>"""


def _bottom_silhouette(fill: str) -> str:
    return f"""
  <g data-silhouette="bottom" stroke-linecap="round" stroke-linejoin="round">
    <path d="M111 68 H209 L218 147 L202 284 H159 L160 151 L151 284 H108 L102 147 Z" fill="{fill}" stroke="{OUTLINE_COLOR}" stroke-width="5"/>
    <path d="M108 105 H212" fill="none" stroke="{DETAIL_COLOR}" stroke-width="4"/>
    <path d="M160 105 V151" fill="none" stroke="{DETAIL_COLOR}" stroke-width="3"/>
  </g>"""


def _shoes_silhouette(fill: str) -> str:
    return f"""
  <g data-silhouette="shoes" stroke-linecap="round" stroke-linejoin="round">
    <path d="M57 183 Q91 181 118 147 Q135 126 159 143 L198 184 Q220 207 259 220 Q277 226 279 245 Q280 263 256 268 H71 Q44 268 42 249 Q41 229 58 219 Z" fill="{fill}" stroke="{OUTLINE_COLOR}" stroke-width="5"/>
    <path d="M52 236 Q112 245 272 239" fill="none" stroke="{DETAIL_COLOR}" stroke-width="4"/>
    <path d="M126 161 L181 184 M114 174 L170 197 M102 188 L157 210" fill="none" stroke="{DETAIL_COLOR}" stroke-width="4"/>
  </g>"""


SILHOUETTES = {
    "top": _top_silhouette,
    "bottom": _bottom_silhouette,
    "shoes": _shoes_silhouette,
}


def build_product_svg(product: dict[str, str]) -> str:
    """从一条已校验的 CSV 商品记录生成无外部资源的 SVG。"""
    product_id = product["id"].strip()
    category = product["category"].strip()
    color_name = product["color"].strip()

    match = PRODUCT_ID_PATTERN.fullmatch(product_id)
    if match is None:
        raise ValueError(f"无效商品 ID：{product_id}")
    try:
        expected_prefix, kind = CATEGORY_METADATA[category]
    except KeyError as error:
        raise ValueError(f"无效商品类别：{category}") from error
    if match.group(1) != expected_prefix:
        raise ValueError(f"商品 ID 与类别不匹配：{product_id}")
    try:
        fill = COLOR_PALETTE[color_name]
    except KeyError as error:
        raise ValueError(f"缺少颜色映射：{color_name}") from error

    safe_id = escape(product_id)
    safe_category = escape(category)
    safe_color = escape(color_name)
    silhouette = SILHOUETTES[kind](fill)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!-- 由 scripts/generate_product_assets.py 确定性生成。 -->
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 360" role="img" aria-labelledby="title desc" data-product-id="{safe_id}" data-category="{safe_category}" data-kind="{kind}" data-color="{safe_color}">
  <title id="title">{safe_category}商品示意图</title>
  <desc id="desc">本地程序生成的演示示意图，不代表真实商品外观</desc>
  <rect width="320" height="360" rx="28" fill="{BACKGROUND_COLOR}"/>
  <rect x="12" y="12" width="296" height="336" rx="22" fill="{CARD_COLOR}" stroke="#D9DEE6" stroke-width="2"/>
{silhouette}
  <rect x="84" y="304" width="152" height="32" rx="16" fill="{LABEL_COLOR}"/>
  <text x="160" y="326" text-anchor="middle" font-family="sans-serif" font-size="15" font-weight="600" fill="{TEXT_COLOR}">演示示意图</text>
</svg>
"""


def build_placeholder_svg() -> str:
    """生成商品图片缺失时使用的本地安全占位图。"""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!-- 本地商品图片安全占位图。 -->
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 360" role="img" aria-labelledby="title desc" data-product-id="PLACEHOLDER" data-category="占位图" data-kind="placeholder">
  <title id="title">商品图片暂缺</title>
  <desc id="desc">本地演示占位图，不代表真实商品外观</desc>
  <rect width="320" height="360" rx="28" fill="{BACKGROUND_COLOR}"/>
  <rect x="12" y="12" width="296" height="336" rx="22" fill="{CARD_COLOR}" stroke="#D9DEE6" stroke-width="2"/>
  <rect x="76" y="85" width="168" height="150" rx="20" fill="#EEF1F5" stroke="{OUTLINE_COLOR}" stroke-width="4"/>
  <path d="M95 210 L137 166 L166 193 L193 157 L226 210 Z" fill="#CBD2DC" stroke="{OUTLINE_COLOR}" stroke-width="3" stroke-linejoin="round"/>
  <circle cx="122" cy="127" r="16" fill="#D7DDE5" stroke="{OUTLINE_COLOR}" stroke-width="3"/>
  <text x="160" y="278" text-anchor="middle" font-family="sans-serif" font-size="18" font-weight="600" fill="{TEXT_COLOR}">商品图片暂缺</text>
  <text x="160" y="307" text-anchor="middle" font-family="sans-serif" font-size="14" fill="#667085">本地演示占位图</text>
</svg>
"""


def load_demo_products(csv_path: Path = DATA_PATH) -> list[dict[str, str]]:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        products = list(csv.DictReader(csv_file))
    if len(products) != 24:
        raise ValueError("演示商品 CSV 必须恰好包含 24 条商品")
    return products


def _write_svg(path: Path, content: str) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as output:
        output.write(content)


def generate_assets() -> list[Path]:
    """写入 24 个商品 SVG 和一个通用占位图。"""
    ASSET_DIRECTORY.mkdir(parents=True, exist_ok=True)
    generated: list[Path] = []
    for product in load_demo_products():
        product_id = product["id"].strip()
        output_path = ASSET_DIRECTORY / f"{product_id}.svg"
        _write_svg(output_path, build_product_svg(product))
        generated.append(output_path)

    placeholder_path = ASSET_DIRECTORY / PLACEHOLDER_FILENAME
    _write_svg(placeholder_path, build_placeholder_svg())
    generated.append(placeholder_path)
    return generated


if __name__ == "__main__":
    paths = generate_assets()
    print(f"已生成 {len(paths) - 1} 个商品示意图和 1 个占位图：{ASSET_DIRECTORY}")
