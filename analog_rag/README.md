# Analog RAG（与 lina_code_new 一致的做法）

基于 `analog_test1` 目录下的解决方案构建 RAG 检索，采用与 **lina_code_new** 相同的流程：**四类关键词（解决方案类型 / 技术类型 / 核心组件 / 性能指标） + 向量化 + FAISS + 按类别加权得分**，并接入 `generdatedata.py` 的 `system_gen`，在生成系统框图前注入相似历史方案。

## 数据约定

- **方案库**：`analog_test1` 下每个**子目录**为一个方案（须包含 `complete_data.json`）。
- **方案 ID**：子目录名（如 `心电图(ECG)测量解决方案`、`下一代气象雷达`）。
- **检索用文本**（用于四类关键词提取与向量化）包括：
  - `complete_data.json`：`page_info`、`value_and_benefits`；
  - `signal_chain_mapping_for_rag.json`：各信号链的 `description_preview`；
  - **`signal_chain_descriptions/signal_chain_{chain_id}_fast.json`**：`devices`（器件名+描述）、`signal_flow`（主/分支）、`application_scene`；
  - **选型表 CSV**：通过 `signal_chain_{chain_id}_description_to_csv_mapping.json` 的 `mapping`（模块→csv_files）找到 `exports_signal_chain_csv/` 下对应 CSV，读取 **Part#（型号）** 与 **Description/参数**，按「信号链-模块」拼入文本。
- **检索结果返回**：除 title/description/characteristic 外，会带上 **信号链模块与可选型号参数**（同上 CSV 型号与参数摘要），供 generdatedata 的 LLM 参考选型。

## 构建索引（两步）

### 1. 关键词提取（需 LLM）

对每个方案用大模型按四类提取关键词，结果写入 `analog_rag_output/keyword_extraction/*_extraction.json`。

- 需配置与 `server_wb` 一致的 API（如火山方舟），可通过 `static/key1.txt` 或环境变量 `LLM_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL` 配置。

### 2. 向量化并写出 npy/csv/scheme_details

```bash
# 在项目根目录执行
python -m analog_rag.run_build
```

- 会读取 `analog_rag_output/keyword_extraction/` 下所有 `*_extraction.json`，用 **SentenceTransformer**（`aspire/acge_text_embedding`，与 lina 一致）做向量化。
- 输出目录：`analog_rag_output/embeddings/`
  - `keyword_embeddings.npy`
  - `keyword_metadata.csv`（列：scheme_id, category, keyword）
  - `scheme_details.json`（scheme_id -> title, description, characteristic，供前端/LLM 展示）。

## 接入 generdatedata

- 在 **server_wb** 中已接好：当环境变量 **`ANALOG_RAG_ENABLE=1`** 时，会优先使用 Analog RAG 检索器（若索引存在），并传给 `noBaseGenerator(..., rag_retriever=rag_retriever)`。
- 可选：`ANALOG_RAG_EMBEDDINGS_DIR` 指定索引目录，不设则使用默认 `analog_rag_output/embeddings`。

启动前：

1. 已运行过 `python -m analog_rag.run_build` 生成索引。
2. 设置 `ANALOG_RAG_ENABLE=1`（或 `true`/`yes`）后启动服务。

检索接口与现有 RAG 一致：

- `retrieve_similar_cases(query, top_k=3, similarity_threshold=0.6)` → 返回相似方案列表。
- `format_cases_for_llm(similar_cases, max_tokens=800)` → 格式化为注入 `template_analysis` / `template_system` 的 `expert_cases` 文本。

## 目录结构小结

```
analog_rag/
  __init__.py
  config.py
  collect_solutions.py   # 扫描 analog_test1，收集方案与文本
  keyword_extractor.py   # LLM 四类关键词提取
  embed_keywords.py      # 向量化，写 npy/csv/scheme_details
  retriever.py           # FAISS 检索 + AnalogSchemeRAGRetriever
  run_build.py           # 一键：提取 -> 向量化
analog_rag_output/
  keyword_extraction/    # 各方案 *_extraction.json
  embeddings/            # keyword_embeddings.npy, keyword_metadata.csv, scheme_details.json
```

## 依赖

- `sentence-transformers`（与 lina 一致，建议使用 `aspire/acge_text_embedding`，需本地已有或可下载）
- `faiss`（或 `faiss-cpu`）
- `openai`（兼容火山方舟等 OpenAI 接口）
- `pandas`、`numpy`
