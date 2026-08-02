import base64
from pathlib import Path

from streamlit.testing.v1 import AppTest


APP_PATH = Path(__file__).parents[1] / "app.py"
NOTICE = "当前版本仅支持图片上传与预览，图片分析功能将在下一版本接入。"
ONE_PIXEL_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def test_page_works_without_an_uploaded_image():
    app = AppTest.from_file(APP_PATH).run()

    assert not app.exception
    assert len(app.file_uploader) == 1
    assert app.file_uploader[0].allowed_type == [".jpg", ".jpeg", ".png"]
    assert any(message.value == NOTICE for message in app.info)
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

    generate_button = next(button for button in app.button if button.label == "生成穿搭")
    generate_button.click().run()

    assert any(message.value == "找到 3 套符合条件的搭配" for message in app.success)
    assert len(app.image) == 1
