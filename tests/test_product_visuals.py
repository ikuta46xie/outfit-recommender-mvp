from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from product_visuals import (
    PRODUCT_ASSET_DIRECTORY,
    placeholder_image_path,
    product_image_path,
)
from recommender import load_products
from scripts.generate_product_assets import (
    build_placeholder_svg,
    build_product_svg,
    load_demo_products,
)


PROJECT_ROOT = Path(__file__).parents[1]
DATA_PATH = PROJECT_ROOT / "data" / "products.csv"


def _root(path: Path) -> ET.Element:
    return ET.parse(path).getroot()


def test_all_24_catalog_products_have_nonempty_local_svg_assets():
    products = load_products(DATA_PATH)

    assert len(products) == 24
    for product in products:
        path = product_image_path(product.id)
        assert path == PRODUCT_ASSET_DIRECTORY / f"{product.id}.svg"
        assert path.is_file()
        assert path.stat().st_size > 0
        root = _root(path)
        assert root.attrib["data-product-id"] == product.id
        assert root.attrib["data-color"] == product.color
        assert root.attrib["viewBox"] == "0 0 320 360"


@pytest.mark.parametrize(
    ("product_id", "expected_category", "expected_kind", "silhouette"),
    [
        ("TOP001", "上衣", "top", "top"),
        ("BOTTOM001", "裤子", "bottom", "bottom"),
        ("SHOES001", "鞋子", "shoes", "shoes"),
    ],
)
def test_each_category_uses_the_correct_distinct_silhouette(
    product_id, expected_category, expected_kind, silhouette
):
    root = _root(product_image_path(product_id))
    groups = [element for element in root.iter() if element.attrib.get("data-silhouette")]

    assert root.attrib["data-category"] == expected_category
    assert root.attrib["data-kind"] == expected_kind
    assert [group.attrib["data-silhouette"] for group in groups] == [silhouette]


def test_every_svg_is_valid_xml_and_contains_no_active_or_external_content():
    paths = sorted(PRODUCT_ASSET_DIRECTORY.glob("*.svg"))
    assert len(paths) == 25

    for path in paths:
        root = _root(path)
        assert root.tag.endswith("svg")
        assert path.read_text(encoding="utf-8").strip()
        for element in root.iter():
            local_tag = element.tag.rsplit("}", 1)[-1].casefold()
            assert local_tag not in {"script", "foreignobject", "image", "iframe"}
            for attribute, value in element.attrib.items():
                local_attribute = attribute.rsplit("}", 1)[-1].casefold()
                assert local_attribute not in {"href", "src"}
                lowered = value.casefold()
                assert "url(" not in lowered
                assert "data:" not in lowered
                assert "base64" not in lowered


def test_white_products_keep_a_visible_nonwhite_outline():
    white_ids = [product.id for product in load_products(DATA_PATH) if product.color == "白色"]
    assert white_ids

    for product_id in white_ids:
        root = _root(product_image_path(product_id))
        white_shapes = [
            element
            for element in root.iter()
            if element.attrib.get("fill", "").upper() == "#FFFFFF"
            and element.attrib.get("stroke", "").upper() not in {"", "#FFFFFF"}
            and float(element.attrib.get("stroke-width", "0")) > 0
        ]
        assert white_shapes


def test_missing_valid_id_uses_the_local_placeholder():
    placeholder = placeholder_image_path()

    assert placeholder.is_file()
    assert product_image_path("TOP999") == placeholder
    assert _root(placeholder).attrib["data-kind"] == "placeholder"


@pytest.mark.parametrize(
    "malicious_id",
    [
        "../README",
        "..\\README",
        "/tmp/TOP001",
        "C:\\Windows\\system.ini",
        "TOP001/../../README",
        "TOP001.svg",
        "top001",
        "",
    ],
)
def test_invalid_ids_and_path_traversal_cannot_escape_the_asset_directory(malicious_id):
    assert product_image_path(malicious_id) == placeholder_image_path()


def test_committed_assets_exactly_match_the_deterministic_generator():
    products = load_demo_products(DATA_PATH)

    for product in products:
        path = PRODUCT_ASSET_DIRECTORY / f"{product['id']}.svg"
        assert path.read_text(encoding="utf-8") == build_product_svg(product)
    assert placeholder_image_path().read_text(encoding="utf-8") == build_placeholder_svg()


def test_runtime_visual_modules_contain_no_remote_image_urls():
    for relative_path in ("app.py", "product_visuals.py"):
        source = (PROJECT_ROOT / relative_path).read_text(encoding="utf-8").casefold()
        assert "http://" not in source
        assert "https://" not in source
