"""Streamlit 穿搭推荐 MVP。"""

from pathlib import Path

import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError

from anchor_item import (
    ANCHOR_CATEGORIES,
    CATEGORY_UNSPECIFIED,
    AnchorItem,
    AnchorValidationError,
    build_confirmed_anchor,
    confirmed_anchor_for,
    infer_anchor_defaults,
    store_confirmed_anchor,
)
from anchor_recommender import AnchoredOutfit, recommend_anchor_outfits
from image_preferences import (
    REFERENCE_STYLES,
    UNSPECIFIED,
    ImagePreference,
    build_confirmed_preference,
    confirmed_preference_for,
    infer_preference_defaults,
    store_confirmed_preference,
)
from product_visuals import placeholder_image_path, product_image_path
from recommender import Outfit, Product, load_products, recommend_outfits
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
ANCHOR_MODE = "围绕图片单品"
st.set_page_config(page_title="AI 穿搭推荐助手", page_icon="👔", layout="wide")


@st.cache_data
def available_colors() -> list[str]:
    return sorted({product.color for product in load_products(DATA_PATH)})


@st.cache_data
def available_shoe_sizes() -> list[str]:
    sizes = {
        size
        for product in load_products(DATA_PATH)
        if product.category == "鞋子"
        for size in product.sizes
    }
    return sorted(sizes, key=int)


def show_product_card(label: str, product: Product) -> None:
    """用本地示意图和 CSV 真实字段展示一个演示商品。"""
    with st.container(border=True):
        st.image(
            str(product_image_path(product.id)),
            caption=f"{label}商品示意图",
            use_column_width=True,
        )
        st.caption("🏷️ 演示商品")
        st.markdown(f"**{product.name}**")
        st.caption(f"类别：{label}")
        st.caption(f"颜色：{product.color}")
        st.caption(f"可用尺码：{' / '.join(product.sizes)}")
        st.markdown(f"**价格：¥{product.price}**")


def show_outfit_metrics(outfit: Outfit, *, image_guided: bool) -> None:
    if image_guided:
        total, base, bonus = st.columns(3)
        total.metric("总价", f"¥{outfit.total_price}")
        base.metric("基础匹配分", f"{outfit.base_score:.1f}")
        bonus.metric("图片偏好加分", f"+{outfit.image_preference_bonus:.1f}")
        st.markdown("**推荐理由**")
        for reason in outfit.recommendation_reasons:
            st.caption(f"• {reason}")
    else:
        total, score = st.columns(2)
        total.metric("总价", f"¥{outfit.total_price}")
        score.metric("匹配分", f"{outfit.score:.1f}")


def show_outfit(index: int, outfit: Outfit, *, image_guided: bool = False) -> None:
    with st.container(border=True):
        st.subheader(f"搭配 {index}")
        columns = st.columns(3, gap="small")
        for column, label, item in zip(columns, ("上衣", "裤子", "鞋子"), (outfit.top, outfit.bottom, outfit.shoes)):
            with column:
                show_product_card(label, item)
        show_outfit_metrics(outfit, image_guided=image_guided)


def show_anchor_slot(
    label: str,
    anchor: AnchorItem,
    anchor_preview: bytes | None,
) -> None:
    """仅使用本次运行内存中的当前上传图展示自有锚点。"""
    with st.container(border=True):
        if anchor_preview is not None:
            st.image(
                anchor_preview,
                caption="我的单品",
                use_column_width=True,
            )
        else:
            st.image(
                str(placeholder_image_path()),
                caption="我的单品图片不可用",
                use_column_width=True,
            )
        st.caption("📌 我的单品")
        st.markdown(f"**{anchor.name}**")
        st.caption(f"类别：{label}")
        st.caption(f"确认颜色：{anchor.primary_color or UNSPECIFIED}")
        st.caption(f"确认风格：{anchor.style or UNSPECIFIED}")
        st.caption("自有单品，不计入预算")


def show_anchored_outfit(
    index: int,
    outfit: AnchoredOutfit,
    anchor_preview: bytes | None,
) -> None:
    with st.container(border=True):
        st.subheader(f"搭配 {index}")
        columns = st.columns(3, gap="small")
        for column, category in zip(columns, ("上衣", "裤子", "鞋子")):
            item = outfit.item_for_category(category)
            with column:
                if isinstance(item, AnchorItem):
                    show_anchor_slot(category, item, anchor_preview)
                else:
                    show_product_card(category, item)
        total, base, bonus = st.columns(3)
        total.metric("需购买商品总价", f"¥{outfit.total_price}")
        base.metric("基础匹配分", f"{outfit.base_score:.1f}")
        bonus.metric("锚点匹配加分", f"+{outfit.anchor_match_bonus:.1f}")
        st.markdown("**推荐理由**")
        for reason in outfit.recommendation_reasons:
            st.caption(f"• {reason}")


def show_result_header(mode: str, count: int) -> None:
    st.divider()
    st.subheader("推荐结果")
    st.caption(f"当前模式：{mode}｜找到 {count} 套搭配")
    st.caption("商品图片为本地生成的演示示意图，不代表真实商品外观。")


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


def show_anchor_confirmation(
    result: VisionAnalysis, cache_key: str
) -> AnchorItem | None:
    """展示锚点单品确认模块；确认动作本身不会触发视觉 API。"""
    colors = available_colors()
    automatic_name, automatic_category, automatic_color, automatic_style = (
        infer_anchor_defaults(
            result.category,
            result.items,
            result.primary_color,
            result.style_tags,
            colors,
        )
    )
    category_options = [CATEGORY_UNSPECIFIED, *ANCHOR_CATEGORIES]
    color_options = [UNSPECIFIED, *colors]
    style_options = [*REFERENCE_STYLES, UNSPECIFIED]

    with st.container(border=True):
        st.subheader("围绕图片中的单品搭配")
        st.info(
            "此功能适合主体明确的单件服装图片；如图片中有多件服装，请手动确认要使用的单品。"
        )
        selected_name = st.text_input(
            "单品名称",
            value=automatic_name,
            max_chars=30,
            key=f"anchor_name_{cache_key}",
        )
        selected_category = st.selectbox(
            "单品类别",
            category_options,
            index=category_options.index(automatic_category),
            key=f"anchor_category_{cache_key}",
        )
        selected_color = st.selectbox(
            "单品主色",
            color_options,
            index=color_options.index(automatic_color),
            key=f"anchor_color_{cache_key}",
        )
        selected_style = st.selectbox(
            "单品风格",
            style_options,
            index=style_options.index(automatic_style),
            key=f"anchor_style_{cache_key}",
        )
        if st.button(
            "确认这件单品并补全搭配",
            key=f"confirm_anchor_{cache_key}",
        ):
            try:
                anchor = build_confirmed_anchor(
                    cache_key,
                    automatic_name=automatic_name,
                    automatic_category=automatic_category,
                    automatic_color=automatic_color,
                    automatic_style=automatic_style,
                    selected_name=selected_name,
                    selected_category=selected_category,
                    selected_color=selected_color,
                    selected_style=selected_style,
                    available_colors=colors,
                )
            except AnchorValidationError as error:
                st.error(error.user_message)
            else:
                store_confirmed_anchor(st.session_state, anchor)
                st.success("自有单品已确认，可选择“围绕图片单品”模式。")

    return confirmed_anchor_for(st.session_state, cache_key)


st.title("👔 AI 穿搭推荐助手")
st.write("可使用普通推荐、参考图片偏好或围绕图片单品三种模式，从本地演示商品中组合最多三套穿搭。")
st.info("当前商品均为演示数据，不代表真实库存、价格或购买链接。")
st.caption("商品图片为本地生成的演示示意图，不代表真实商品外观。")

current_cache_key: str | None = None
current_image_preference: ImagePreference | None = None
current_anchor_item: AnchorItem | None = None
current_anchor_preview: bytes | None = None

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
            current_anchor_preview = processed_image.jpeg_bytes
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
                    current_anchor_item = show_anchor_confirmation(
                        analysis_result,
                        cache_key,
                    )

available_modes = [NORMAL_MODE]
if current_image_preference is not None:
    available_modes.append(IMAGE_GUIDED_MODE)
if current_anchor_item is not None:
    available_modes.append(ANCHOR_MODE)

st.divider()
st.subheader("推荐条件")
with st.form("recommendation_form"):
    recommendation_mode = st.radio(
        "推荐模式",
        available_modes,
        horizontal=len(available_modes) > 1,
        disabled=len(available_modes) == 1,
        key=f"recommendation_mode_{current_cache_key or 'without_image'}",
    )
    if len(available_modes) == 1:
        st.caption("完成图片分析并确认偏好或自有单品后，可使用对应推荐模式。")
    scene = st.selectbox("场景", ["通勤", "休闲", "约会", "旅行"])
    budget_label = (
        "补全单品预算（不含自有单品）"
        if recommendation_mode == ANCHOR_MODE
        else "整套预算（元）"
    )
    budget = st.slider(budget_label, 600, 2000, 1200, 50)
    left, middle, right = st.columns(3)
    with left:
        top_size = st.selectbox("上衣尺码", ["S", "M", "L", "XL"], index=1)
    with middle:
        bottom_size = st.selectbox("裤子尺码", ["S", "M", "L", "XL"], index=1)
    with right:
        shoe_sizes = available_shoe_sizes()
        shoe_size = st.selectbox(
            "鞋码",
            shoe_sizes,
            index=shoe_sizes.index("40"),
            help="仅在围绕图片单品且需要推荐鞋子时参与筛选。",
        )
    style = st.selectbox("风格", ["简约", "休闲", "商务", "运动"])
    excluded_colors = st.multiselect("排除颜色（可多选）", available_colors())
    if recommendation_mode == IMAGE_GUIDED_MODE:
        st.info("图片偏好只影响排序，预算、尺码和排除颜色仍为硬性条件。")
    elif recommendation_mode == ANCHOR_MODE:
        st.info("自有单品不计入预算；预算、尺码、场景、原风格和排除颜色仍是硬性条件。")
    submitted = st.form_submit_button("生成穿搭", type="primary", use_container_width=True)

if submitted:
    if recommendation_mode == ANCHOR_MODE and current_anchor_item is not None:
        anchored_outfits = recommend_anchor_outfits(
            DATA_PATH,
            anchor=current_anchor_item,
            budget=budget,
            top_size=top_size,
            bottom_size=bottom_size,
            shoe_size=shoe_size,
            scene=scene,
            style=style,
            excluded_colors=excluded_colors,
            limit=3,
        )
        show_result_header(recommendation_mode, len(anchored_outfits))
        if not anchored_outfits:
            st.warning("当前条件下没有可补齐的搭配，请提高补全预算或减少筛选条件。")
        else:
            st.success(f"找到 {len(anchored_outfits)} 套补全搭配")
            for number, outfit in enumerate(anchored_outfits, start=1):
                show_anchored_outfit(number, outfit, current_anchor_preview)
    else:
        preference = (
            current_image_preference
            if recommendation_mode == IMAGE_GUIDED_MODE
            else None
        )
        outfits = recommend_outfits(DATA_PATH, budget=budget, top_size=top_size,
            bottom_size=bottom_size, scene=scene, style=style,
            excluded_colors=excluded_colors, limit=3,
            image_preference=preference)
        show_result_header(recommendation_mode, len(outfits))
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
