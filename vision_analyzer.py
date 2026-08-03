"""千问视觉分析、图片内存预处理与响应校验。"""

from __future__ import annotations

import base64
import hashlib
import json
import re
import warnings
from collections.abc import Callable, Mapping, MutableMapping, MutableSet
from dataclasses import dataclass
from io import BytesIO
from typing import Any

from openai import (
    APIConnectionError,
    APIError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    OpenAI,
    RateLimitError,
)
from PIL import Image, ImageOps, UnidentifiedImageError


DEFAULT_MODEL = "qwen3.7-flash"
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_IMAGE_PIXELS = 40_000_000
MAX_IMAGE_EDGE = 1280
JPEG_QUALITY = 85
REQUEST_TIMEOUT_SECONDS = 30.0
MAX_RETRIES = 1
MAX_OUTPUT_TOKENS = 700
SESSION_IMAGE_LIMIT = 3

_WORKSPACE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
_REQUIRED_FIELDS = {
    "is_clothing_image",
    "category",
    "items",
    "primary_color",
    "secondary_colors",
    "style_tags",
    "pattern",
    "silhouette",
    "material_guess",
    "description",
    "uncertain_fields",
    "confidence",
}
_LIST_LIMITS = {
    "items": 6,
    "secondary_colors": 3,
    "style_tags": 4,
    "silhouette": 4,
    "material_guess": 3,
    "uncertain_fields": 4,
}

ANALYSIS_PROMPT = """请分析图片中的服装，并且只返回一个 JSON 对象，不要输出 Markdown、代码块或额外说明。

JSON 必须严格包含以下字段：
{
  "is_clothing_image": true,
  "category": "套装",
  "items": ["黑色长款西装", "黑色马甲", "黑色长裤"],
  "primary_color": "黑色",
  "secondary_colors": ["深灰色"],
  "style_tags": ["暗黑", "前卫", "解构正装"],
  "pattern": "纯色",
  "silhouette": ["宽肩", "长款", "宽松"],
  "material_guess": ["西装面料"],
  "description": "不超过80个中文字符的简短描述",
  "uncertain_fields": ["具体面料"],
  "confidence": 0.82
}

约束：items最多6项，secondary_colors最多3项，style_tags最多4项，silhouette最多4项，
material_guess最多3项，uncertain_fields最多4项，confidence必须在0到1之间。
只描述有明确图像证据的服装；不确定内容放入uncertain_fields。
不得推断品牌、价格、人物身份、年龄、性别、身材或其他敏感个人属性。
不要堆砌缺乏图像证据的Y2K、哥特、机能风等标签。
如果图片中没有清晰服装，将is_clothing_image设为false，所有字符串设为空字符串，
所有数组设为空数组，confidence设为0.0。"""


class ImageProcessingError(ValueError):
    """可安全展示给用户的图片处理错误。"""

    def __init__(self, code: str, user_message: str) -> None:
        super().__init__(user_message)
        self.code = code
        self.user_message = user_message


class AnalysisValidationError(ValueError):
    """模型 JSON 不满足应用字段约束。"""


class VisionServiceError(RuntimeError):
    """不包含上游异常细节的安全服务错误。"""

    def __init__(self, code: str, user_message: str) -> None:
        super().__init__(user_message)
        self.code = code
        self.user_message = user_message


@dataclass(frozen=True)
class QwenConfig:
    api_key: str
    workspace_id: str
    model: str = DEFAULT_MODEL

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any] | None) -> QwenConfig | None:
        if values is None:
            return None
        api_key = values.get("api_key")
        workspace_id = values.get("workspace_id")
        model = values.get("model", DEFAULT_MODEL)
        if not isinstance(api_key, str) or not api_key.strip():
            return None
        if not isinstance(workspace_id, str) or not _WORKSPACE_ID_PATTERN.fullmatch(workspace_id.strip()):
            return None
        if model is None or model == "":
            model = DEFAULT_MODEL
        if not isinstance(model, str) or not model.strip():
            return None
        return cls(api_key=api_key.strip(), workspace_id=workspace_id.strip(), model=model.strip())


@dataclass(frozen=True)
class ProcessedImage:
    jpeg_bytes: bytes
    data_url: str
    width: int
    height: int


@dataclass(frozen=True)
class VisionAnalysis:
    is_clothing_image: bool
    category: str
    items: tuple[str, ...]
    primary_color: str
    secondary_colors: tuple[str, ...]
    style_tags: tuple[str, ...]
    pattern: str
    silhouette: tuple[str, ...]
    material_guess: tuple[str, ...]
    description: str
    uncertain_fields: tuple[str, ...]
    confidence: float


def build_beijing_base_url(workspace_id: str) -> str:
    """仅构造百炼华北2（北京）业务空间兼容端点。"""
    if not _WORKSPACE_ID_PATTERN.fullmatch(workspace_id):
        raise ValueError("Invalid workspace ID")
    return f"https://{workspace_id}.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"


def image_sha256(image_bytes: bytes) -> str:
    return hashlib.sha256(image_bytes).hexdigest()


def analysis_cache_key(image_hash: str, model: str) -> str:
    return f"{image_hash}:{model or DEFAULT_MODEL}"


def prepare_image(image_bytes: bytes) -> ProcessedImage:
    """在内存中校验、纠正方向、缩放并压缩为 JPEG Data URL。"""
    if not image_bytes:
        raise ImageProcessingError("invalid_image", "图片为空，请重新选择一张服装图片。")
    if len(image_bytes) > MAX_UPLOAD_BYTES:
        raise ImageProcessingError(
            "file_too_large",
            f"图片文件过大，请上传不超过 {MAX_UPLOAD_BYTES // 1024 // 1024}MB 的图片。",
        )

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(image_bytes)) as source:
                width, height = source.size
                if width <= 0 or height <= 0 or width * height > MAX_IMAGE_PIXELS:
                    raise ImageProcessingError("dimensions_too_large", "图片尺寸过大，请上传较小的图片。")
                source.load()
                corrected = ImageOps.exif_transpose(source)
                rgb_image = corrected.convert("RGB")
                rgb_image.thumbnail((MAX_IMAGE_EDGE, MAX_IMAGE_EDGE), Image.Resampling.LANCZOS)
                output = BytesIO()
                rgb_image.save(output, format="JPEG", quality=JPEG_QUALITY, optimize=True)
                jpeg_bytes = output.getvalue()
                processed_width, processed_height = rgb_image.size
    except ImageProcessingError:
        raise
    except (Image.DecompressionBombWarning, Image.DecompressionBombError):
        raise ImageProcessingError("dimensions_too_large", "图片尺寸过大，请上传较小的图片。") from None
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError):
        raise ImageProcessingError("invalid_image", "图片无法读取或已损坏，请重新选择 JPG、JPEG 或 PNG 图片。") from None

    encoded = base64.b64encode(jpeg_bytes).decode("ascii")
    return ProcessedImage(
        jpeg_bytes=jpeg_bytes,
        data_url=f"data:image/jpeg;base64,{encoded}",
        width=processed_width,
        height=processed_height,
    )


def _read_string(payload: Mapping[str, Any], field: str) -> str:
    value = payload[field]
    if not isinstance(value, str):
        raise AnalysisValidationError(f"{field} must be a string")
    return value.strip()


def _read_string_list(payload: Mapping[str, Any], field: str) -> tuple[str, ...]:
    value = payload[field]
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise AnalysisValidationError(f"{field} must be a string list")
    cleaned = tuple(item.strip() for item in value)
    if any(not item for item in cleaned):
        raise AnalysisValidationError(f"{field} contains an empty item")
    if len(cleaned) > _LIST_LIMITS[field]:
        raise AnalysisValidationError(f"{field} has too many items")
    return cleaned


def parse_analysis_json(raw_content: str) -> VisionAnalysis:
    """解析并严格校验模型返回的单个 JSON 对象。"""
    try:
        payload = json.loads(raw_content)
    except (json.JSONDecodeError, TypeError):
        raise AnalysisValidationError("invalid JSON") from None
    if not isinstance(payload, dict):
        raise AnalysisValidationError("response must be a JSON object")

    missing = _REQUIRED_FIELDS - payload.keys()
    unexpected = payload.keys() - _REQUIRED_FIELDS
    if missing:
        raise AnalysisValidationError("missing required fields")
    if unexpected:
        raise AnalysisValidationError("unexpected fields")

    is_clothing_image = payload["is_clothing_image"]
    if not isinstance(is_clothing_image, bool):
        raise AnalysisValidationError("is_clothing_image must be boolean")

    category = _read_string(payload, "category")
    primary_color = _read_string(payload, "primary_color")
    pattern = _read_string(payload, "pattern")
    description = _read_string(payload, "description")
    if len(description) > 80:
        raise AnalysisValidationError("description is too long")

    items = _read_string_list(payload, "items")
    secondary_colors = _read_string_list(payload, "secondary_colors")
    style_tags = _read_string_list(payload, "style_tags")
    silhouette = _read_string_list(payload, "silhouette")
    material_guess = _read_string_list(payload, "material_guess")
    uncertain_fields = _read_string_list(payload, "uncertain_fields")

    confidence = payload["confidence"]
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        raise AnalysisValidationError("confidence must be numeric")
    confidence = float(confidence)
    if not 0.0 <= confidence <= 1.0:
        raise AnalysisValidationError("confidence is out of range")

    if not is_clothing_image:
        string_values = (category, primary_color, pattern, description)
        list_values = (items, secondary_colors, style_tags, silhouette, material_guess, uncertain_fields)
        if any(string_values) or any(list_values) or confidence != 0.0:
            raise AnalysisValidationError("non-clothing response must use empty fields")

    return VisionAnalysis(
        is_clothing_image=is_clothing_image,
        category=category,
        items=items,
        primary_color=primary_color,
        secondary_colors=secondary_colors,
        style_tags=style_tags,
        pattern=pattern,
        silhouette=silhouette,
        material_guess=material_guess,
        description=description,
        uncertain_fields=uncertain_fields,
        confidence=confidence,
    )


def analyze_prepared_image(
    image: ProcessedImage,
    config: QwenConfig,
    *,
    client_factory: Callable[..., Any] = OpenAI,
) -> VisionAnalysis:
    """调用百炼 OpenAI 兼容 Chat Completions 并返回已校验结果。"""
    client = client_factory(
        api_key=config.api_key,
        base_url=build_beijing_base_url(config.workspace_id),
        timeout=REQUEST_TIMEOUT_SECONDS,
        max_retries=MAX_RETRIES,
    )
    try:
        response = client.chat.completions.create(
            model=config.model or DEFAULT_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": image.data_url}},
                        {"type": "text", "text": ANALYSIS_PROMPT},
                    ],
                }
            ],
            response_format={"type": "json_object"},
            extra_body={"enable_thinking": False},
            temperature=0.1,
            max_completion_tokens=MAX_OUTPUT_TOKENS,
        )
    except AuthenticationError:
        raise VisionServiceError("authentication", "AI分析服务鉴权失败，请联系管理员检查配置。") from None
    except APITimeoutError:
        raise VisionServiceError("timeout", "AI分析请求超时，请稍后重试。") from None
    except RateLimitError:
        raise VisionServiceError("rate_limit", "AI分析服务额度不足或请求过于频繁，请稍后重试。") from None
    except APIConnectionError:
        raise VisionServiceError("network", "AI分析服务暂时无法连接，请稍后重试。") from None
    except APIStatusError as error:
        if error.status_code in (401, 403):
            raise VisionServiceError("authentication", "AI分析服务鉴权失败，请联系管理员检查配置。") from None
        if error.status_code == 429:
            raise VisionServiceError("rate_limit", "AI分析服务额度不足或请求过于频繁，请稍后重试。") from None
        raise VisionServiceError("service", "AI分析服务暂时不可用，请稍后重试。") from None
    except APIError:
        raise VisionServiceError("service", "AI分析服务暂时不可用，请稍后重试。") from None

    try:
        content = response.choices[0].message.content
    except (AttributeError, IndexError, TypeError):
        raise VisionServiceError("invalid_json", "AI分析返回格式无效，请重试。") from None
    if not isinstance(content, str) or not content.strip():
        raise VisionServiceError("invalid_json", "AI分析返回格式无效，请重试。")

    try:
        return parse_analysis_json(content)
    except AnalysisValidationError as error:
        code = "invalid_json" if str(error) in {"invalid JSON", "response must be a JSON object"} else "validation"
        message = "AI分析返回格式无效，请重试。" if code == "invalid_json" else "AI分析结果校验失败，请重试。"
        raise VisionServiceError(code, message) from None


def analyze_with_session_cache(
    image_bytes: bytes,
    processed_image: ProcessedImage,
    config: QwenConfig,
    result_cache: MutableMapping[str, VisionAnalysis],
    attempted_keys: MutableSet[str],
    seen_image_hashes: MutableSet[str],
    *,
    analyzer: Callable[[ProcessedImage, QwenConfig], VisionAnalysis] = analyze_prepared_image,
    image_limit: int = SESSION_IMAGE_LIMIT,
) -> tuple[VisionAnalysis, bool]:
    """执行会话级去重与三张不同图片限制；缓存中只保存分析结果。"""
    image_hash = image_sha256(image_bytes)
    cache_key = analysis_cache_key(image_hash, config.model)
    cached = result_cache.get(cache_key)
    if cached is not None:
        return cached, True
    if cache_key in attempted_keys:
        raise VisionServiceError("duplicate_attempt", "本次会话已尝试分析此图片，请更换图片后再试。")
    if image_hash not in seen_image_hashes and len(seen_image_hashes) >= image_limit:
        raise VisionServiceError("session_limit", "本次会话最多分析3张不同图片。")

    attempted_keys.add(cache_key)
    seen_image_hashes.add(image_hash)
    result = analyzer(processed_image, config)
    result_cache[cache_key] = result
    return result, False
