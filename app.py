"""Streamlit 穿搭推荐 MVP。"""

from pathlib import Path

import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError

from recommender import Outfit, load_products, recommend_outfits
from vision_analyzer import (
    DEFAULT_MODEL,
    ImageProcessingError,
    QwenConfig,
    VisionAnalysis,
    VisionServiceError,
    analysis_cache_key,
    analyze_with_session_cache,
    image_sha256,
    prepare_image,
)


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


def load_qwen_config() -> QwenConfig | None:
    try:
        values = st.secrets["qwen"]
    except (KeyError, FileNotFoundError, OSError, StreamlitSecretNotFoundError):
        return None
    return QwenConfig.from_mapping(values)


def show_analysis_result(result: VisionAnalysis) -> None:
    if not result.is_clothing_image:
        st.warning("没有识别到清晰的服装，请上传主体明确、光线充足的服装图片。")
        return

    st.success("AI 服装分析完成")
    st.write(result.description)
    left, right = st.columns(2)
    with left:
        st.markdown(f"**类别：** {result.category or '未识别'}")
        st.markdown(f"**主要颜色：** {result.primary_color or '未识别'}")
        st.markdown(f"**其他颜色：** {'、'.join(result.secondary_colors) or '无'}")
        st.markdown(f"**图案：** {result.pattern or '未识别'}")
    with right:
        st.markdown(f"**单品：** {'、'.join(result.items) or '未识别'}")
        st.markdown(f"**风格标签：** {'、'.join(result.style_tags) or '未识别'}")
        st.markdown(f"**廓形：** {'、'.join(result.silhouette) or '未识别'}")
        st.markdown(f"**材质推测：** {'、'.join(result.material_guess) or '未识别'}")
    st.progress(result.confidence, text=f"置信度：{result.confidence:.0%}")
    st.caption(f"不确定项：{'、'.join(result.uncertain_fields) or '无'}")


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
    if uploaded_image is not None:
        uploaded_bytes = uploaded_image.getvalue()
        try:
            processed_image = prepare_image(uploaded_bytes)
        except ImageProcessingError as error:
            st.error(error.user_message)
        else:
            st.image(processed_image.jpeg_bytes, caption="图片预览", width=360)
            st.caption(f"文件名：{uploaded_image.name}")
            st.info("点击分析后，图片将临时发送至阿里云百炼进行识别；本站不会保存图片。")

            config = load_qwen_config()
            model = config.model if config is not None else DEFAULT_MODEL
            upload_hash = image_sha256(uploaded_bytes)
            cache_key = analysis_cache_key(upload_hash, model)

            if "vision_analysis_cache" not in st.session_state:
                st.session_state["vision_analysis_cache"] = {}
            if "vision_attempted_keys" not in st.session_state:
                st.session_state["vision_attempted_keys"] = set()
            if "vision_seen_image_hashes" not in st.session_state:
                st.session_state["vision_seen_image_hashes"] = set()

            consent = st.checkbox(
                "我已了解图片将临时发送至阿里云百炼进行分析",
                key=f"vision_consent_{upload_hash}",
            )
            cached_result = st.session_state["vision_analysis_cache"].get(cache_key)
            analyze_clicked = st.button(
                "AI 分析服装",
                disabled=not consent or config is None or cached_result is not None,
                key=f"vision_analyze_{cache_key}",
            )

            if cached_result is not None:
                st.caption("已使用当前会话缓存结果，未重复调用 AI 服务。")
                show_analysis_result(cached_result)
            elif config is None:
                st.warning("AI分析服务尚未配置")
            elif analyze_clicked:
                with st.spinner("正在分析服装图片…"):
                    try:
                        result, _ = analyze_with_session_cache(
                            uploaded_bytes,
                            processed_image,
                            config,
                            st.session_state["vision_analysis_cache"],
                            st.session_state["vision_attempted_keys"],
                            st.session_state["vision_seen_image_hashes"],
                        )
                    except VisionServiceError as error:
                        st.error(error.user_message)
                    except Exception:
                        st.error("AI分析服务暂时不可用，请稍后重试。")
                    else:
                        show_analysis_result(result)

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
