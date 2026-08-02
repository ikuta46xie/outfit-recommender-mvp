# 穿搭推荐 MVP

一个无需大模型、图片识别、登录或数据库的 Streamlit 中文穿搭推荐应用。当前版本基于本地 CSV 演示商品和可解释规则进行筛选与排序，并支持上传服装图片进行页面预览。

> `data/products.csv` 中的 24 条商品均为“演示数据（非真实库存）”，不代表真实价格、库存或购买链接。

## 功能

- V0.2 支持上传 JPG、JPEG 或 PNG 服装图片，并以受控宽度在页面中预览文件名和图片
- 当前图片仅用于上传与预览，不参与推荐，也不会调用视觉 API 或保存到仓库
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

## 测试

```bash
python -m pytest
```

测试覆盖图片上传与预览、图片不影响推荐、预算限制、尺码匹配、排除颜色、商品来源、搭配去重，以及演示数据数量和分类。

## 主要数据流

1. `app.py` 在内存中接收可选图片并进行预览；图片不会传入推荐器。
2. `app.py` 独立收集用户筛选条件，未上传图片时表单功能保持不变。
3. `recommender.py` 读取并校验 `data/products.csv`。
4. 推荐器分别筛选上衣、裤子和鞋子，再生成合法三件套组合。
5. 丢弃超预算组合，其余组合按基础匹配分、总价和商品 ID 确定性排序。
6. 在基础排序上贪心重排，优先选取与已选结果重复商品 ID 最少的搭配。
7. Streamlit 展示最多三套结果、单品信息及总价。

## 项目结构

```text
.
├── app.py
├── recommender.py
├── data/products.csv
├── tests/test_app.py
├── tests/test_recommender.py
├── requirements.txt
└── README.md
```
