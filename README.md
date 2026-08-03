# 穿搭推荐 MVP

一个 Streamlit 中文穿搭推荐应用。V0.5 支持把上传图片中经用户确认的自有单品作为锚点，从演示商品库补齐另外两个类别。

> `data/products.csv` 中的 24 条商品均为“演示数据（非真实库存）”，不代表真实价格、库存或购买链接。

## 功能

- V0.3 使用 `qwen3.7-flash` 可选分析 JPG、JPEG 或 PNG 服装图片
- 只有用户确认隐私提示并主动点击“AI 分析服装”后才会调用百炼 API
- 图片在内存中纠正 EXIF 方向、缩放至最长边不超过 1280px，并压缩为 JPEG 后临时发送
- 千问原始标签只用于预填“参考主色”和“参考风格”，不会直接进入推荐器
- 用户可修改预填值；只有点击“确认并用于推荐”后，偏好才会绑定当前图片哈希与模型并保存在当前会话
- 保留“普通推荐”，并新增“参考图片偏好”模式；普通模式的基础评分与排序保持不变
- 图片偏好仅作为有上限的软加分影响排序，预算、尺码、场景、原表单风格和排除颜色始终是硬约束
- 确认偏好、调整推荐条件和生成穿搭均不会增加千问 API 调用
- V0.5 可确认图片中的上衣、裤子或鞋子，并分别补齐裤子＋鞋子、上衣＋鞋子或上衣＋裤子
- 自有锚点使用独立数据结构，不属于 CSV 商品，不显示或虚构商品 ID、价格、库存、尺码和购买信息
- 补全预算只计算需要购买的两个 CSV 商品；自有单品不计入预算
- 锚点名称、类别、主色和风格必须由用户确认，且确认结果绑定当前图片与模型缓存键
- 普通推荐和 V0.4“参考图片偏好”模式继续保留，三种模式互相独立
- V0.5 不是虚拟试穿，不生成服装、人物或穿着效果图
- 确认锚点、修改条件和生成补全搭配不会增加千问 API 调用
- 当前会话对同图同模型复用分析结果，并限制最多分析 3 张不同图片
- 按场景、整套预算、上衣尺码、裤子尺码、风格和排除颜色筛选
- 每套搭配固定包含上衣、裤子和鞋子，且总价不超过预算
- 所有推荐商品严格来自 CSV，不会生成不存在的商品
- 使用“基础匹配评分 + 多样性重排”：先按预算匹配度、配色和标签丰富度评分，再优先选择商品重复更少的组合
- 多样性重排采用确定性贪心算法；商品充足时尽量避免前三套复用单品，商品不足时仍会返回原本可用的搭配

## 本地运行

建议使用 Python 3.10 或更高版本。

```bash
python -m venv .venv
# Windows PowerShell
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
streamlit run app.py
```

浏览器将默认打开 `http://localhost:8501`。

## 千问视觉配置

项目使用百炼华北2（北京）地域的 OpenAI 兼容接口。复制占位示例并在本地填写自己的配置：

```toml
[qwen]
api_key = "your-api-key"
workspace_id = "your-workspace-id"
model = "qwen3.7-flash"
```

配置应保存为 `.streamlit/secrets.toml`；该文件已被 `.gitignore` 忽略，不应提交到 GitHub。仓库中的 `.streamlit/secrets.example.toml` 仅包含占位符。未配置 Secrets 时页面会提示“AI分析服务尚未配置”，原有推荐仍可正常使用。

## 图片隐私与安全

- 原图和压缩图均只在内存中处理，不写入磁盘、数据库或 GitHub
- 只有点击分析按钮后，压缩图片才会临时发送至阿里云百炼
- 会话缓存仅保存经过字段校验的分析结果，以及图片哈希等去重元数据，不保存图片内容
- 应用不会展示上游原始异常、API Key、Workspace ID、Base URL 或图片 Base64

## 测试

```bash
python -m pytest
```

测试覆盖图片缩放与 EXIF 方向、Base64 Data URL、JSON 字段校验、API 请求参数、错误映射、会话缓存与费用限制、未配置服务降级，以及全部原有推荐行为。测试通过模拟客户端运行，不会调用真实千问 API。

V0.4 还覆盖颜色与风格别名映射、用户修改优先级、图片缓存键绑定、普通模式回归、图片软加分与推荐理由、硬约束不变性、确定性排序及无额外 API 调用。

V0.5 还覆盖锚点类别映射、名称校验、缓存键绑定、三类补全组合、鞋码和其他硬约束、仅购买商品计价、锚点软评分、真实理由、多样性重排、三模式回归及无额外 API 调用。

## 主要数据流

1. `app.py` 接收可选图片；`vision_analyzer.py` 在内存中校验、纠正方向、缩放并压缩图片。
2. 用户确认并点击分析后，应用用 OpenAI Python SDK 调用北京地域百炼 Chat Completions API。
3. `vision_analyzer.py` 解析 JSON，并严格校验字段类型、数量、描述长度和置信度范围。
4. `app.py` 用当前 Streamlit 会话保存分析结果和哈希去重元数据，展示标签、描述、置信度及不确定项。
5. `image_preferences.py` 将已校验视觉字段确定性映射为可编辑预填值；用户确认后才生成与当前图片缓存键绑定的结构化偏好。
6. `anchor_item.py` 结合视觉类别和单品名称生成可编辑预填值；用户确认名称、类别、颜色和风格后才保存独立 `AnchorItem`。
7. `recommender.py` 保持普通推荐与图片偏好模式；先按预算、尺码、场景、原风格和排除颜色生成合法三件套。
8. `anchor_recommender.py` 根据锚点类别只组合缺少的两个 CSV 类别，并按补全预算、对应尺码（含鞋码）、场景、原风格和排除颜色应用硬约束。
9. 两类推荐器分别计算既有图片偏好分或锚点匹配分，按最终分确定性排序后执行多样性贪心重排。
10. Streamlit 展示最多三套结果；锚点位置明确标记为“我的单品”和“不计入预算”。

## 项目结构

```text
.
├── app.py
├── anchor_item.py
├── anchor_recommender.py
├── image_preferences.py
├── recommender.py
├── vision_analyzer.py
├── data/products.csv
├── .streamlit/secrets.example.toml
├── tests/test_app.py
├── tests/test_anchor_item.py
├── tests/test_anchor_recommender.py
├── tests/test_image_preferences.py
├── tests/test_recommender.py
├── tests/test_vision_analyzer.py
├── requirements.txt
└── README.md
```
