# 穿搭推荐 MVP

一个 Streamlit 中文穿搭推荐应用。V0.3 在本地规则推荐之外，新增可选的阿里云百炼千问视觉分析；视觉结果暂不参与推荐。

> `data/products.csv` 中的 24 条商品均为“演示数据（非真实库存）”，不代表真实价格、库存或购买链接。

## 功能

- V0.3 使用 `qwen3.7-flash` 可选分析 JPG、JPEG 或 PNG 服装图片
- 只有用户确认隐私提示并主动点击“AI 分析服装”后才会调用百炼 API
- 图片在内存中纠正 EXIF 方向、缩放至最长边不超过 1280px，并压缩为 JPEG 后临时发送
- 视觉分析结果只用于页面展示，暂不影响现有推荐条件、评分或排序
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

## 主要数据流

1. `app.py` 接收可选图片；`vision_analyzer.py` 在内存中校验、纠正方向、缩放并压缩图片。
2. 用户确认并点击分析后，应用用 OpenAI Python SDK 调用北京地域百炼 Chat Completions API。
3. `vision_analyzer.py` 解析 JSON，并严格校验字段类型、数量、描述长度和置信度范围。
4. `app.py` 用当前 Streamlit 会话保存分析结果和哈希去重元数据，展示标签、描述、置信度及不确定项。
5. 图片和分析结果均不会传入 `recommend_outfits`；推荐流程与视觉分析相互独立。
6. `recommender.py` 读取并校验 `data/products.csv`，筛选并生成合法三件套组合。
7. 合法组合按基础匹配分确定性排序，再进行多样性贪心重排。
8. Streamlit 展示最多三套推荐结果、单品信息及总价。

## 项目结构

```text
.
├── app.py
├── recommender.py
├── vision_analyzer.py
├── data/products.csv
├── .streamlit/secrets.example.toml
├── tests/test_app.py
├── tests/test_recommender.py
├── tests/test_vision_analyzer.py
├── requirements.txt
└── README.md
```
