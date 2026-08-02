"""Streamlit 穿搭推荐 MVP。"""

from pathlib import Path

import streamlit as st

from recommender import Outfit, load_products, recommend_outfits


DATA_PATH = Path(__file__).parent / "data" / "products.csv"
st.set_page_config(page_title="穿搭推荐 MVP", page_icon="👔", layout="centered")


@st.cache_data
def available_colors() -> list[str]:
    return sorted({product.color for product in load_products(DATA_PATH)})


def show_product(label: str, product_name: str, color: str, price: int, size: str) -> None:
    st.markdown(f"**{label}｜{product_name}**")
    st.caption(f"{color} · {size} · ¥{price}")


def show_outfit(index: int, outfit: Outfit) -> None:
    with st.container(border=True):
        st.subheader(f"搭配 {index}")
        columns = st.columns(3)
        for column, label, item in zip(columns, ("上衣", "裤子", "鞋子"), (outfit.top, outfit.bottom, outfit.shoes)):
            with column:
                show_product(label, item.name, item.color, item.price, "/".join(item.sizes))
        st.markdown(f"**总价：¥{outfit.total_price}**　匹配分：{outfit.score:.1f}")


st.title("👔 穿搭推荐 MVP")
st.write("选择你的需求，我们会从本地演示商品中组合最多三套穿搭。")
st.info("当前商品均为演示数据，不代表真实库存、价格或购买链接。")

with st.container(border=True):
    st.subheader("上传服装图片")
    uploaded_image = st.file_uploader(
        "选择一张服装照片",
        type=["jpg", "jpeg", "png"],
        help="支持 JPG、JPEG 和 PNG 格式。",
    )
    st.info("当前版本仅支持图片上传与预览，图片分析功能将在下一版本接入。")
    if uploaded_image is not None:
        st.image(uploaded_image, caption="图片预览", width=360)
        st.caption(f"文件名：{uploaded_image.name}")

with st.form("recommendation_form"):
    scene = st.selectbox("场景", ["通勤", "休闲", "约会", "旅行"])
    budget = st.slider("整套预算（元）", 600, 2000, 1200, 50)
    left, right = st.columns(2)
    with left:
        top_size = st.selectbox("上衣尺码", ["S", "M", "L", "XL"], index=1)
    with right:
        bottom_size = st.selectbox("裤子尺码", ["S", "M", "L", "XL"], index=1)
    style = st.selectbox("风格", ["简约", "休闲", "商务", "运动"])
    excluded_colors = st.multiselect("排除颜色（可多选）", available_colors())
    submitted = st.form_submit_button("生成穿搭", type="primary", use_container_width=True)

if submitted:
    outfits = recommend_outfits(DATA_PATH, budget=budget, top_size=top_size,
        bottom_size=bottom_size, scene=scene, style=style,
        excluded_colors=excluded_colors, limit=3)
    if not outfits:
        st.warning("当前条件下没有符合预算的完整搭配，请提高预算或减少筛选条件。")
    else:
        st.success(f"找到 {len(outfits)} 套符合条件的搭配")
        for number, outfit in enumerate(outfits, start=1):
            show_outfit(number, outfit)
