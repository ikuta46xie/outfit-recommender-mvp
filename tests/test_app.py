import base64
from io import BytesIO
from pathlib import Path
from unittest.mock import Mock

from PIL import Image
from streamlit.testing.v1 import AppTest

import vision_analyzer
from anchor_item import confirmed_anchor_for
from image_preferences import confirmed_preference_for
from vision_analyzer import DEFAULT_MODEL, VisionAnalysis, analysis_cache_key, image_sha256


APP_PATH = Path(__file__).parents[1] / "app.py"
PRIVACY_NOTICE = "点击分析后，图片将临时发送至阿里云百炼进行识别；本站不会保存图片。"
ONE_PIXEL_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def clothing_analysis():
    return VisionAnalysis(
        is_clothing_image=True,
        category="套装",
        items=("黑色西装", "灰色西裤"),
        primary_color="深灰",
        secondary_colors=("黑色",),
        style_tags=("暗黑", "解构正装"),
        pattern="纯色",
        silhouette=("宽松",),
        material_guess=("西装面料",),
        description="深灰与黑色组成的正装搭配。",
        uncertain_fields=("具体面料",),
        confidence=0.9,
    )


def single_item_analysis():
    return VisionAnalysis(
        is_clothing_image=True,
        category="上衣",
        items=("黑色西装",),
        primary_color="黑色",
        secondary_colors=("灰色",),
        style_tags=("商务",),
        pattern="纯色",
        silhouette=("合身",),
        material_guess=("西装面料",),
        description="主体明确的黑色西装。",
        uncertain_fields=("具体面料",),
        confidence=0.95,
    )


def cached_analysis_app(analyzer_mock, analysis=None):
    app = AppTest.from_file(APP_PATH).run()
    cache_key = analysis_cache_key(image_sha256(ONE_PIXEL_PNG), DEFAULT_MODEL)
    app.session_state["vision_analysis_cache"] = {cache_key: analysis or clothing_analysis()}
    app.file_uploader[0].set_value(("demo-outfit.png", ONE_PIXEL_PNG, "image/png"))
    app.run()
    assert analyzer_mock.call_count == 0
    return app, cache_key


def different_png():
    output = BytesIO()
    Image.new("RGB", (2, 1), "red").save(output, format="PNG")
    return output.getvalue()


def test_page_works_without_an_uploaded_image():
    app = AppTest.from_file(APP_PATH).run()

    assert not app.exception
    assert len(app.file_uploader) == 1
    assert app.file_uploader[0].allowed_type == [".jpg", ".jpeg", ".png"]
    assert not any(button.label == "AI 分析服装" for button in app.button)
    generate_button = next(button for button in app.button if button.label == "生成穿搭")
    generate_button.click().run()

    assert any(message.value == "找到 3 套符合条件的搭配" for message in app.success)


def test_uploaded_image_is_previewed_with_filename():
    app = AppTest.from_file(APP_PATH).run()
    app.file_uploader[0].set_value(
        ("demo-outfit.png", ONE_PIXEL_PNG, "image/png")
    ).run()

    assert not app.exception
    assert len(app.image) == 1
    assert app.image[0].captions == ["图片预览"]
    assert any(caption.value == "文件名：demo-outfit.png" for caption in app.caption)
    assert any(message.value == PRIVACY_NOTICE for message in app.info)
    assert any(message.value == "AI分析服务尚未配置" for message in app.warning)
    analyze_button = next(button for button in app.button if button.label == "AI 分析服装")
    assert analyze_button.disabled

    generate_button = next(button for button in app.button if button.label == "生成穿搭")
    generate_button.click().run()

    assert any(message.value == "找到 3 套符合条件的搭配" for message in app.success)
    assert len(app.image) == 1


def test_damaged_image_is_rejected_without_breaking_recommendations():
    app = AppTest.from_file(APP_PATH).run()
    app.file_uploader[0].set_value(
        ("broken.png", b"not-an-image", "image/png")
    ).run()

    assert not app.exception
    assert any("图片无法读取或已损坏" in message.value for message in app.error)
    generate_button = next(button for button in app.button if button.label == "生成穿搭")
    generate_button.click().run()
    assert any(message.value == "找到 3 套符合条件的搭配" for message in app.success)


def test_cached_analysis_prefills_editable_confirmed_preferences(monkeypatch):
    analyzer = Mock(side_effect=AssertionError("API must not be called"))
    monkeypatch.setattr(vision_analyzer, "analyze_with_session_cache", analyzer)
    app, cache_key = cached_analysis_app(analyzer)

    color = next(select for select in app.selectbox if select.label == "参考主色")
    style = next(select for select in app.selectbox if select.label == "参考风格")
    assert color.value == "灰色"
    assert style.value == "商务"

    color.select("米色")
    style.select("休闲")
    confirm = next(button for button in app.button if button.label == "确认并用于推荐")
    confirm.click().run()

    preference = confirmed_preference_for(app.session_state, cache_key)
    assert preference is not None
    assert preference.primary_color == "米色"
    assert preference.style == "休闲"
    assert analyzer.call_count == 0


def test_confirming_and_generating_do_not_call_api(monkeypatch):
    analyzer = Mock(side_effect=AssertionError("API must not be called"))
    monkeypatch.setattr(vision_analyzer, "analyze_with_session_cache", analyzer)
    app, _ = cached_analysis_app(analyzer)

    confirm = next(button for button in app.button if button.label == "确认并用于推荐")
    confirm.click().run()
    mode = next(radio for radio in app.radio if radio.label == "推荐模式")
    assert mode.options == ["普通推荐", "参考图片偏好"]
    mode.set_value("参考图片偏好").run()
    generate = next(button for button in app.button if button.label == "生成穿搭")
    generate.click().run()

    assert analyzer.call_count == 0
    assert any("图片偏好加分" in markdown.value for markdown in app.markdown)


def test_new_image_does_not_reuse_old_confirmed_preference(monkeypatch):
    analyzer = Mock(side_effect=AssertionError("API must not be called"))
    monkeypatch.setattr(vision_analyzer, "analyze_with_session_cache", analyzer)
    app, old_cache_key = cached_analysis_app(analyzer)
    next(button for button in app.button if button.label == "确认并用于推荐").click().run()
    assert confirmed_preference_for(app.session_state, old_cache_key) is not None

    new_bytes = different_png()
    app.file_uploader[0].set_value(("another.png", new_bytes, "image/png")).run()

    mode = next(radio for radio in app.radio if radio.label == "推荐模式")
    assert mode.options == ["普通推荐"]
    assert mode.disabled
    assert analyzer.call_count == 0


def test_anchor_item_can_be_edited_confirmed_and_used_without_api(monkeypatch):
    analyzer = Mock(side_effect=AssertionError("API must not be called"))
    monkeypatch.setattr(vision_analyzer, "analyze_with_session_cache", analyzer)
    app, cache_key = cached_analysis_app(analyzer, single_item_analysis())

    name = next(field for field in app.text_input if field.label == "单品名称")
    category = next(select for select in app.selectbox if select.label == "单品类别")
    color = next(select for select in app.selectbox if select.label == "单品主色")
    style = next(select for select in app.selectbox if select.label == "单品风格")
    assert name.value == "黑色西装"
    assert category.value == "上衣"
    assert color.value == "黑色"
    assert style.value == "商务"

    name.set_value("  我的灰色西裤  ")
    category.select("裤子")
    color.select("灰色")
    style.select("简约")
    confirm_anchor = next(
        button for button in app.button
        if button.label == "确认这件单品并补全搭配"
    )
    confirm_anchor.click().run()

    anchor = confirmed_anchor_for(app.session_state, cache_key)
    assert anchor is not None
    assert (anchor.name, anchor.category, anchor.primary_color, anchor.style) == (
        "我的灰色西裤", "裤子", "灰色", "简约"
    )
    mode = next(radio for radio in app.radio if radio.label == "推荐模式")
    assert mode.options == ["普通推荐", "围绕图片单品"]
    mode.set_value("围绕图片单品").run()
    assert any(slider.label == "补全单品预算（不含自有单品）" for slider in app.slider)
    generate = next(button for button in app.button if button.label == "生成穿搭")
    generate.click().run()

    assert analyzer.call_count == 0
    assert any(message.value == "找到 3 套补全搭配" for message in app.success)
    assert any(caption.value == "自有单品，不计入预算" for caption in app.caption)
    assert any("需购买商品总价" in markdown.value for markdown in app.markdown)


def test_three_modes_are_independently_enabled_after_both_confirmations(monkeypatch):
    analyzer = Mock(side_effect=AssertionError("API must not be called"))
    monkeypatch.setattr(vision_analyzer, "analyze_with_session_cache", analyzer)
    app, _ = cached_analysis_app(analyzer, single_item_analysis())

    next(button for button in app.button if button.label == "确认并用于推荐").click().run()
    next(
        button for button in app.button
        if button.label == "确认这件单品并补全搭配"
    ).click().run()

    mode = next(radio for radio in app.radio if radio.label == "推荐模式")
    assert mode.options == ["普通推荐", "参考图片偏好", "围绕图片单品"]
    assert analyzer.call_count == 0


def test_new_image_does_not_reuse_old_anchor_item(monkeypatch):
    analyzer = Mock(side_effect=AssertionError("API must not be called"))
    monkeypatch.setattr(vision_analyzer, "analyze_with_session_cache", analyzer)
    app, old_cache_key = cached_analysis_app(analyzer, single_item_analysis())
    next(
        button for button in app.button
        if button.label == "确认这件单品并补全搭配"
    ).click().run()
    assert confirmed_anchor_for(app.session_state, old_cache_key) is not None

    new_bytes = different_png()
    app.file_uploader[0].set_value(("another.png", new_bytes, "image/png")).run()

    mode = next(radio for radio in app.radio if radio.label == "推荐模式")
    assert mode.options == ["普通推荐"]
    assert mode.disabled
    assert analyzer.call_count == 0
