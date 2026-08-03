import base64
from pathlib import Path

from streamlit.testing.v1 import AppTest


APP_PATH = Path(__file__).parents[1] / "app.py"
PRIVACY_NOTICE = "点击分析后，图片将临时发送至阿里云百炼进行识别；本站不会保存图片。"
ONE_PIXEL_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


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
