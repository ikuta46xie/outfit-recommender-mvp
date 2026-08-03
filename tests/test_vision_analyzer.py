import base64
import json
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from openai import APIConnectionError, APITimeoutError, AuthenticationError, RateLimitError
from PIL import Image

from recommender import recommend_outfits
from vision_analyzer import (
    ANALYSIS_PROMPT,
    DEFAULT_MODEL,
    MAX_IMAGE_EDGE,
    MAX_UPLOAD_BYTES,
    ImageProcessingError,
    ProcessedImage,
    QwenConfig,
    VisionAnalysis,
    VisionServiceError,
    analysis_cache_key,
    analyze_prepared_image,
    analyze_with_session_cache,
    build_beijing_base_url,
    image_sha256,
    parse_analysis_json,
    prepare_image,
)


DATA_PATH = Path(__file__).parents[1] / "data" / "products.csv"
VALID_PAYLOAD = {
    "is_clothing_image": True,
    "category": "套装",
    "items": ["黑色长款西装", "黑色马甲", "黑色长裤"],
    "primary_color": "黑色",
    "secondary_colors": ["深灰色"],
    "style_tags": ["暗黑", "前卫", "解构正装"],
    "pattern": "纯色",
    "silhouette": ["宽肩", "长款", "宽松"],
    "material_guess": ["西装面料"],
    "description": "黑色长款西装搭配马甲与长裤，整体线条宽松利落。",
    "uncertain_fields": ["具体面料"],
    "confidence": 0.82,
}


def make_image(width=20, height=10, image_format="PNG", orientation=None):
    image = Image.new("RGB", (width, height), "navy")
    output = BytesIO()
    kwargs = {}
    if orientation is not None:
        exif = Image.Exif()
        exif[274] = orientation
        kwargs["exif"] = exif
    image.save(output, format=image_format, **kwargs)
    return output.getvalue()


def sample_analysis():
    return parse_analysis_json(json.dumps(VALID_PAYLOAD, ensure_ascii=False))


class FakeCompletions:
    def __init__(self, content=None, error=None):
        self.content = content
        self.error = error
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        message = SimpleNamespace(content=self.content)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


class FakeClient:
    def __init__(self, completions):
        self.chat = SimpleNamespace(completions=completions)


def make_client_factory(completions, captured):
    def factory(**kwargs):
        captured.update(kwargs)
        return FakeClient(completions)

    return factory


def test_prepare_image_resizes_and_creates_jpeg_data_url():
    processed = prepare_image(make_image(2000, 1000))

    assert (processed.width, processed.height) == (MAX_IMAGE_EDGE, 640)
    assert processed.data_url.startswith("data:image/jpeg;base64,")
    decoded = base64.b64decode(processed.data_url.split(",", 1)[1])
    assert decoded == processed.jpeg_bytes
    with Image.open(BytesIO(decoded)) as image:
        assert image.mode == "RGB"
        assert image.size == (MAX_IMAGE_EDGE, 640)


def test_prepare_image_corrects_exif_orientation():
    processed = prepare_image(make_image(20, 40, "JPEG", orientation=6))
    assert (processed.width, processed.height) == (40, 20)


def test_prepare_image_rejects_obviously_large_file():
    with pytest.raises(ImageProcessingError) as captured:
        prepare_image(b"x" * (MAX_UPLOAD_BYTES + 1))
    assert captured.value.code == "file_too_large"


def test_valid_json_is_parsed_and_normalized():
    result = sample_analysis()
    assert result.category == "套装"
    assert result.items == ("黑色长款西装", "黑色马甲", "黑色长裤")
    assert result.confidence == pytest.approx(0.82)


@pytest.mark.parametrize(
    "raw_content",
    [
        "not-json",
        json.dumps({key: value for key, value in VALID_PAYLOAD.items() if key != "category"}),
        json.dumps({**VALID_PAYLOAD, "items": "not-a-list"}),
        json.dumps({**VALID_PAYLOAD, "confidence": 1.01}),
    ],
)
def test_invalid_json_or_fields_are_rejected(raw_content):
    with pytest.raises(ValueError):
        parse_analysis_json(raw_content)


def test_false_clothing_result_requires_empty_fields():
    payload = {
        "is_clothing_image": False,
        "category": "",
        "items": [],
        "primary_color": "",
        "secondary_colors": [],
        "style_tags": [],
        "pattern": "",
        "silhouette": [],
        "material_guess": [],
        "description": "",
        "uncertain_fields": [],
        "confidence": 0.0,
    }
    assert not parse_analysis_json(json.dumps(payload)).is_clothing_image


def test_normal_api_response_uses_required_request_options():
    completions = FakeCompletions(json.dumps(VALID_PAYLOAD, ensure_ascii=False))
    client_options = {}
    config = QwenConfig(api_key="placeholder", workspace_id="workspace-test")
    processed = prepare_image(make_image())

    result = analyze_prepared_image(
        processed,
        config,
        client_factory=make_client_factory(completions, client_options),
    )

    assert result.is_clothing_image
    assert client_options == {
        "api_key": "placeholder",
        "base_url": "https://workspace-test.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
        "timeout": 30.0,
        "max_retries": 1,
    }
    request = completions.calls[0]
    assert request["model"] == DEFAULT_MODEL
    assert request["response_format"] == {"type": "json_object"}
    assert request["extra_body"] == {"enable_thinking": False}
    assert request["temperature"] == 0.1
    assert request["max_completion_tokens"] == 700
    assert request["messages"][0]["content"][0]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert "JSON" in ANALYSIS_PROMPT


def make_status_error(error_type, status_code):
    request = httpx.Request("POST", "https://example.invalid/chat/completions")
    response = httpx.Response(status_code, request=request)
    return error_type("safe test error", response=response, body=None)


@pytest.mark.parametrize(
    ("error", "expected_code"),
    [
        (make_status_error(AuthenticationError, 401), "authentication"),
        (APITimeoutError(request=httpx.Request("POST", "https://example.invalid")), "timeout"),
        (make_status_error(RateLimitError, 429), "rate_limit"),
        (APIConnectionError(request=httpx.Request("POST", "https://example.invalid")), "network"),
    ],
)
def test_api_errors_are_mapped_without_raw_details(error, expected_code):
    completions = FakeCompletions(error=error)
    config = QwenConfig(api_key="placeholder", workspace_id="workspace-test")
    with pytest.raises(VisionServiceError) as captured:
        analyze_prepared_image(
            prepare_image(make_image()),
            config,
            client_factory=make_client_factory(completions, {}),
        )
    assert captured.value.code == expected_code
    assert "safe test error" not in captured.value.user_message


@pytest.mark.parametrize(
    ("content", "expected_code"),
    [("not-json", "invalid_json"), (json.dumps({**VALID_PAYLOAD, "confidence": 2}), "validation")],
)
def test_invalid_api_response_has_safe_error(content, expected_code):
    completions = FakeCompletions(content)
    config = QwenConfig(api_key="placeholder", workspace_id="workspace-test")
    with pytest.raises(VisionServiceError) as captured:
        analyze_prepared_image(
            prepare_image(make_image()),
            config,
            client_factory=make_client_factory(completions, {}),
        )
    assert captured.value.code == expected_code


def test_same_image_and_model_use_session_cache_once():
    calls = []
    cache = {}
    attempted_keys = set()
    seen_hashes = set()
    config = QwenConfig(api_key="placeholder", workspace_id="workspace-test")
    image_bytes = make_image()
    processed = prepare_image(image_bytes)

    def analyzer(_processed, _config):
        calls.append("called")
        return sample_analysis()

    first, first_cached = analyze_with_session_cache(
        image_bytes, processed, config, cache, attempted_keys, seen_hashes, analyzer=analyzer
    )
    second, second_cached = analyze_with_session_cache(
        image_bytes, processed, config, cache, attempted_keys, seen_hashes, analyzer=analyzer
    )

    assert first == second
    assert not first_cached
    assert second_cached
    assert calls == ["called"]
    assert list(cache) == [analysis_cache_key(image_sha256(image_bytes), DEFAULT_MODEL)]


def test_failed_same_image_attempt_is_not_called_twice():
    calls = []
    cache = {}
    attempted_keys = set()
    seen_hashes = set()
    config = QwenConfig(api_key="placeholder", workspace_id="workspace-test")
    image_bytes = make_image()
    processed = prepare_image(image_bytes)

    def analyzer(_processed, _config):
        calls.append("called")
        raise VisionServiceError("timeout", "AI分析请求超时，请稍后重试。")

    with pytest.raises(VisionServiceError) as first:
        analyze_with_session_cache(
            image_bytes, processed, config, cache, attempted_keys, seen_hashes, analyzer=analyzer
        )
    with pytest.raises(VisionServiceError) as second:
        analyze_with_session_cache(
            image_bytes, processed, config, cache, attempted_keys, seen_hashes, analyzer=analyzer
        )

    assert first.value.code == "timeout"
    assert second.value.code == "duplicate_attempt"
    assert calls == ["called"]


def test_session_rejects_fourth_distinct_image():
    cache = {}
    attempted_keys = set()
    seen_hashes = set()
    config = QwenConfig(api_key="placeholder", workspace_id="workspace-test")

    def analyzer(_processed, _config):
        return sample_analysis()

    for color in ("red", "green", "blue"):
        output = BytesIO()
        Image.new("RGB", (10, 10), color).save(output, format="PNG")
        image_bytes = output.getvalue()
        analyze_with_session_cache(
            image_bytes,
            prepare_image(image_bytes),
            config,
            cache,
            attempted_keys,
            seen_hashes,
            analyzer=analyzer,
        )

    fourth = make_image(11, 10)
    with pytest.raises(VisionServiceError) as captured:
        analyze_with_session_cache(
            fourth,
            prepare_image(fourth),
            config,
            cache,
            attempted_keys,
            seen_hashes,
            analyzer=analyzer,
        )
    assert captured.value.code == "session_limit"


def test_vision_analysis_does_not_change_recommendations():
    before = recommend_outfits(
        DATA_PATH, budget=1200, top_size="M", bottom_size="M", scene="通勤", style="简约", limit=3
    )
    cache = {}
    attempted_keys = set()
    seen_hashes = set()
    config = QwenConfig(api_key="placeholder", workspace_id="workspace-test")
    image_bytes = make_image()
    analyze_with_session_cache(
        image_bytes,
        prepare_image(image_bytes),
        config,
        cache,
        attempted_keys,
        seen_hashes,
        analyzer=lambda _image, _config: sample_analysis(),
    )
    after = recommend_outfits(
        DATA_PATH, budget=1200, top_size="M", bottom_size="M", scene="通勤", style="简约", limit=3
    )
    assert [outfit.product_ids for outfit in before] == [outfit.product_ids for outfit in after]


def test_default_model_and_beijing_url_helpers():
    config = QwenConfig.from_mapping({"api_key": "placeholder", "workspace_id": "workspace-test"})
    assert config is not None and config.model == DEFAULT_MODEL
    assert build_beijing_base_url("workspace-test") == (
        "https://workspace-test.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
    )
