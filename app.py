"""Streamlit 穿搭推荐 MVP。"""

from pathlib import Path

import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError

from image_preferences import (
    REFERENCE_STYLES,
    UNSPECIFIED,
    ImagePreference,
    build_confirmed_preference,
    confirmed_preference_for,
    infer_preference_defaults,
    store_confirmed_preference,
)
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
NORMAL_MODE = "普通推荐"
IMAGE_GUIDED_MODE = "参考图片偏好"
st.set_page_config(page_title="穿搭推荐 MVP", page_icon="👔", layout="centered")


@st.cache_data
def available_colors() -> list[str]:
    return sorted({product.color for product in load_products(DATA_PATH)})


def show_product(label: str, product_name: str, color: str, price: int, size: str) -> None:
    st.markdown(f"**{label}｜{product_name}**")
    st.caption(f"{color} · {size} · ¥{price}")


def show_outfit(index: int, outfit: Outfit, *, image_guided: bool = False) -> None:
    with st.container(border=True):
        st.subheader(f"搭配 {index}")
        columns = st.columns(3)
        for column, label, item in zip(columns, ("上衣", "裤子", "鞋子"), (outfit.top, outfit.bottom, outfit.shoes)):
            with column:
                show_product(label, item.name, item.color, item.price, "/".join(item.sizes))
        if image_guided:
            st.markdown(
                f"**总价：¥{outfit.total_price}**　"
                f"基础匹配分：{outfit.base_score:.1f}　"
                f"图片偏好加分：+{outfit.image_preference_bonus:.1f}"
            )
            for reason in outfit.recommendation_reasons:
                st.caption(f"• {reason}")
        else:
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


def show_preference_confirmation(
    result: VisionAnalysis, cache_key: str
) -> ImagePreference | None:
    """展示可编辑的标准化偏好，并仅在用户确认后写入会话状态。"""
    colors = available_colors()
    automatic_color, automatic_style = infer_preference_defaults(
        result.primary_color,
        result.style_tags,
        colors,
    )
    color_options = [UNSPECIFIED, *colors]
    style_options = [*REFERENCE_STYLES, UNSPECIFIED]

    with st.container(border=True):
        st.subheader("确认用于推荐的图片偏好")
        st.caption("AI 标签仅用于生成可编辑预填值；确认前不会进入推荐器。")
        selected_color = st.selectbox(
            "参考主色",
            color_options,
            index=color_options.index(automatic_color),
            key=f"image_preference_color_{cache_key}",
        )
        selected_style = st.selectbox(
            "参考风格",
            style_options,
            index=style_options.index(automatic_style),
            key=f"image_preference_style_{cache_key}",
        )
        if st.button("确认并用于推荐", key=f"confirm_image_preference_{cache_key}"):
            preference = build_confirmed_preference(
                cache_key,
                automatic_color=automatic_color,
                automatic_style=automatic_style,
                selected_color=selected_color,
                selected_style=selected_style,
                available_colors=colors,
            )
            store_confirmed_preference(st.session_state, preference)
            st.success("图片偏好已确认，可在推荐条件中选择“参考图片偏好”。")

    return confirmed_preference_for(st.session_state, cache_key)


st.title("👔 穿搭推荐 MVP")
st.write("选择你的需求，我们会从本地演示商品中组合最多三套穿搭。")
st.info("当前商品均为演示数据，不代表真实库存、价格或购买链接。")

current_cache_key: str | None = None
current_image_preference: ImagePreference | None = None

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
            current_cache_key = cache_key

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

            analysis_result: VisionAnalysis | None = None
            if cached_result is not None:
                st.caption("已使用当前会话缓存结果，未重复调用 AI 服务。")
                analysis_result = cached_result
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
                        analysis_result = result

            if analysis_result is not None:
                show_analysis_result(analysis_result)
                if analysis_result.is_clothing_image:
                    current_image_preference = show_preference_confirmation(
                        analysis_result,
                        cache_key,
                    )

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
    if current_image_preference is None:
        recommendation_mode = st.radio(
            "推荐模式",
            [NORMAL_MODE],
            disabled=True,
            key="recommendation_mode_without_preference",
        )
        st.caption("完成图片分析并确认偏好后，可使用“参考图片偏好”模式。")
    else:
        recommendation_mode = st.radio(
            "推荐模式",
            [NORMAL_MODE, IMAGE_GUIDED_MODE],
            horizontal=True,
            key=f"recommendation_mode_{current_cache_key}",
        )
        if recommendation_mode == IMAGE_GUIDED_MODE:
            st.info("图片偏好只影响排序，预算、尺码和排除颜色仍为硬性条件。")
    submitted = st.form_submit_button("生成穿搭", type="primary", use_container_width=True)

if submitted:
    preference = (
        current_image_preference
        if recommendation_mode == IMAGE_GUIDED_MODE
        else None
    )
    outfits = recommend_outfits(DATA_PATH, budget=budget, top_size=top_size,
        bottom_size=bottom_size, scene=scene, style=style,
        excluded_colors=excluded_colors, limit=3,
        image_preference=preference)
    if not outfits:
        st.warning("当前条件下没有符合预算的完整搭配，请提高预算或减少筛选条件。")
    else:
        st.success(f"找到 {len(outfits)} 套符合条件的搭配")
        for number, outfit in enumerate(outfits, start=1):
            show_outfit(
                number,
                outfit,
                image_guided=recommendation_mode == IMAGE_GUIDED_MODE,
            )
