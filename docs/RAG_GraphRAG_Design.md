# ADI 解决方案数据增强 + RAG + 知识图谱 + GraphRAG 整体流程设计

## 一、目标与现状

- **目标**：在方案设计（`/generate_all`）前引入「ADI 解决方案 + 型号参数」作为参考，先做向量 RAG，再引入知识图谱与 GraphRAG，提升参考方案的相关性和可解释性。
- **现状**：
  - `analog_devices_data_test/` 下已有按解决方案爬取的结构化 JSON（`complete_data.json`），内含型号、描述、`product_link`，但**缺少你想要的参数**（如工作电压、封装、温度范围等）。
  - 现有 RAG（`catch_from_html/rag_expert_search.py`）面向另一类历史方案数据（CRM 项目结构），通过 `RAG_DATA_PATH` / `RAG_INDEX_PATH` 加载，在 `generdatedata.system_gen` 中注入 `expert_cases_text` 给分析/生成 prompt。

---

## 二、整体流程总览（四阶段 + 接入点）

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│ 阶段 0：已有数据                                                                  │
│   analog_devices_data_test/ 各 solution/complete_data.json + products_list.csv   │
│   → 有 型号、描述、product_link，缺 详细参数                                       │
└─────────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│ 阶段 1：数据增强（crawl4ai + LLM 抽取）                                            │
│   • 从 JSON 收集所有 product_link（去重）                                         │
│   • 用 crawl4ai 爬取每个产品页                                                    │
│   • LLM 从页面内容中抽取「你需要的参数」→ 写入 型号级 增强 JSON / 写入原 JSON       │
│   • 输出：enriched_solutions/ 或 增强后的 complete_data（含 product_params）      │
└─────────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│ 阶段 2：向量 RAG 构建与接入                                                        │
│   • 将「解决方案 + 增强后型号参数」转成可检索文本（chunk 策略）                     │
│   • 用现有 embedding（如 HuggingFaceEmbeddings）建 FAISS 索引                     │
│   • 方案设计前：query = 用户 intention → 检索 top_k 条 → 格式化给 system_gen       │
│   • 可与现有 expert_case RAG 并存：ADI 方案 RAG + 历史项目 RAG 双路检索再合并      │
└─────────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│ 阶段 3：知识图谱构建                                                               │
│   • 实体：Solution、Product、Parameter、SignalChain、Category 等                   │
│   • 关系：Solution -[CONTAINS]-> Product, Product -[HAS_PARAM]-> Parameter,        │
│           Solution -[HAS_SIGNAL_CHAIN]-> SignalChain, Product -[BELONGS_TO]-> Cat│
│   • 存储：Neo4j / NetworkX + 持久化 / 或 图数据库                                 │
│   • 数据源：enriched_solutions（含参数）+ complete_data 中的 signal_chains         │
└─────────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│ 阶段 4：GraphRAG 与检索融合                                                        │
│   • 方案 A：子图摘要（社区检测 → 每个社区生成摘要 → 检索时先匹配社区再取子图）       │
│   • 方案 B：多跳遍历（从 query 命中实体 → 沿边扩展 1～2 跳 → 子图文本喂给 LLM）     │
│   • 与向量 RAG 融合：先向量检索得到候选 solution/product，再用图扩展相邻节点       │
│   • 输出：GraphRAG 得到的「相关子图/路径描述」与向量 RAG 的 chunk 一起拼成参考上下文 │
└─────────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│ 接入点：方案设计主流程（server_wb + generdatedata）                               │
│   • /generate_all 触发时：                                                        │
│     1) intention → ADI_RAG 检索（向量 + 可选 GraphRAG）→ expert_cases_text_adi   │
│     2) 可选：原有历史方案 RAG → expert_cases_text_legacy                         │
│     3) 合并 expert_cases_text = expert_cases_text_adi + expert_cases_text_legacy │
│     4) system_gen(intention, expert_cases=expert_cases_text) 保持不变             │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 三、阶段 1：用 crawl4ai + LLM 补全型号参数（数据增强）

### 3.1 输入与输出

- **输入**：
  - `analog_devices_data_test/` 下所有 `complete_data.json`。
  - 从每个 JSON 的 `hardware_products`、`evaluation_products`、`reference_products` 中收集 `model` + `product_link`（去重，同一 link 只爬一次）。
- **输出**：
  - **方案 A（推荐）**：每个型号一条「增强记录」，存成 `enriched_products.json`（或按 solution 分文件），字段例如：`model`, `product_link`, `solution_title`, `page_url`, `extracted_params`（LLM 抽出的键值对）。
  - **方案 B**：直接回写各 `complete_data.json`，在对应 product 下增加 `extracted_params` 或 `specs` 字段。

### 3.2 单产品页爬取（crawl4ai）

- 对每个 `product_link`：
  - 使用你现有的 `crawl_from_html/qucik_crawl.py` 风格：`CrawlerRunConfig`（如 `delay_before_return_html`、`page_timeout`） + `crawler.arun(url=product_link, config=run_config)`。
  - 取 `result.markdown` 或 `result.cleaned_html` 作为 LLM 输入（建议优先 markdown，省 token）。
- 建议：限速（如每页间隔 1～2s）、失败重试、跳过已存在 `extracted_params` 的型号（支持断点续跑）。

### 3.3 LLM 参数抽取

- **输入**：型号 + 产品页 markdown/html 片段（可截断到前 N 字符以控制 token）。
- **输出**：结构化 JSON，字段由你定义，例如：
  - `工作电压`、`工作温度`、`封装`、`接口类型`、`通道数`、`分辨率`、`带宽`、`功耗`、`典型应用` 等。
- **实现方式**：
  - 用一条「抽取 prompt」+ 你项目里的 LLM（如豆包/DeepSeek），要求只输出 JSON。
  - 若页面无某参数则填 `null` 或「未提及」。对同一 `product_link` 可只爬一次，对多 solution 共享的型号可只抽一次，再写回多条 product 引用。

### 3.4 与现有目录的关系

- 保持 `analog_devices_data_test/` 的目录结构不变，仅增加：
  - 要么在每 solution 下增加 `enriched_products.json`（model → extracted_params），
  - 要么在根目录建 `enriched_solutions/`，按 solution 存「完整 solution JSON + 每个 product 的 extracted_params」。
- 后续阶段 2/3/4 都基于「增强后的 solution + 型号参数」构建。

---

## 四、阶段 2：向量 RAG 构建与接入

### 4.1 可检索文档的构造

- **单位**：以「解决方案」为主文档，必要时辅以「型号级」文档（便于按型号查）。
- **每条文档内容建议包含**：
  - 方案名、`page_info.title`、`description`、`component_overview`、`navigation_path`；
  - 该方案下所有产品的 型号 + 描述 + **你刚抽取的参数**（如 `extracted_params` 拼成一段话）；
  - 若有 `signal_chains`，可加简短描述（如「信号链数：18，包含电机驱动等」）。
- **Chunk 策略**：
  - 若单 solution 文本不太长（< 你的模型 max length），可以 1 solution = 1 chunk；
  - 若较长，可按「方案概述」一个 chunk、「产品列表+参数」一个或多个 chunk 切分，chunk 元数据里带 `solution_id`、`page_url`。

### 4.2 索引与检索

- 使用现有 `langchain_community.embeddings.HuggingFaceEmbeddings`（与 `server_wb` 中一致）对 chunk 做 embedding，用 FAISS 建索引并持久化（如 `./adi_solution_index`）。
- 检索接口：`query = 用户 intention`，返回 top_k（如 5）条 chunk，每条带 `solution_id`、`page_url`、原始 JSON 或关键字段，便于后续拼 `expert_cases_text`。

### 4.3 与 generdatedata 的接入

- 在 `server_wb` 中：
  - 除现有 `rag_retriever`（历史项目）外，增加 **ADI 方案 RAG 检索器**（读同一 embedding 模型 + `adi_solution_index`）。
  - 在 `generate_all` 里，先调用 ADI RAG 得到 `expert_cases_text_adi`，再与原有 `rag_retriever` 的 `expert_cases_text_legacy` 合并（例如字符串拼接），传入 `noBaseGenerator` 的 `system_gen` 所用 prompt 的 `expert_cases` 占位符。
- 这样**方案设计前**就会同时看到「ADI 解决方案 + 型号参数」和「历史项目方案」作为参考，无需改 `template_analysis` 的格式，只需保证 `expert_cases_text` 是模型可读的文本即可。

### 4.4 数据路径建议

- 增强数据：`enriched_solutions/` 或 各 solution 下的 `enriched_products.json`。
- RAG 索引：`RAG_INDEX_PATH_ADI=./adi_solution_index`，数据源路径 `RAG_DATA_PATH_ADI` 指向「从 enriched 数据生成的文档列表或 JSON」（可单独写一个「从 enriched 生成 RAG 文档」的脚本）。

---

## 五、阶段 3：知识图谱构建

### 5.1 实体设计（示例）

| 实体类型   | 属性示例 |
|------------|----------|
| Solution   | id, title, page_url, description, navigation_path |
| Product    | id, model, category, product_link, description |
| Parameter  | id, name_cn, name_en, value, unit（可选挂到 Product） |
| SignalChain| id, chain_id, list_name, image_path |
| Category   | id, name（如「产品特性」「评估板与套件」） |

### 5.2 关系设计（示例）

- `Solution -[CONTAINS]-> Product`（从 complete_data 的 hardware_products 等）
- `Product -[HAS_PARAM]-> Parameter`（从 LLM 抽取的 extracted_params）
- `Product -[IN_CATEGORY]-> Category`
- `Solution -[HAS_SIGNAL_CHAIN]-> SignalChain`（从 signal_chains.chains）
- 若要做「型号替代」可后续加：`Product -[REPLACES]-> Product` 等。

### 5.3 存储与实现

- **选项 A**：Neo4j — 适合生产、多跳查询和可视化，需部署 Neo4j 服务。
- **选项 B**：NetworkX + 持久化（如 pickle / JSON 导出）— 轻量，适合先跑通 GraphRAG 逻辑，再迁到 Neo4j。
- **数据来源**：遍历所有 enriched solution JSON，按上述实体和关系插入节点与边；signal_chains 从 `complete_data.json` 的 `signal_chains.chains` 来。

### 5.4 与 RAG 的衔接

- 图谱中的 `Solution`、`Product` 的 id 与 RAG 文档的 `solution_id`、`model` 对应，便于「向量检索得到 solution/product → 在图里取子图」。

---

## 六、阶段 4：GraphRAG 与检索融合

### 6.1 GraphRAG 两种常见用法

- **社区摘要（Microsoft GraphRAG 风格）**：
  - 对图做社区检测（如 Louvain），每个社区生成一段自然语言摘要（LLM）；
  - 检索时：用 query 的 embedding 与「社区摘要」做相似度，选 top 社区，再把这些社区内的节点/边转成文本，作为上下文给 LLM。
- **多跳扩展**：
  - 用 query 先在向量 RAG 里命中若干 Solution/Product（或先用关键词在图里匹配实体）；
  - 从这些实体出发，在图上游走 1～2 跳（如 Solution → Product → Parameter），把路径或子图转成「某方案包含型号 A，A 有参数电压=3.3V…」的文本；
  - 将该文本与向量 RAG 的 chunk 一起作为 `expert_cases_text` 的一部分。

### 6.2 与现有流程的融合建议

- **两阶段检索**：
  1. **向量 RAG**：intention → 检索 ADI 方案 top_k 条 + 可选历史方案 top_k 条 → 得到候选 solution/product 的 id 或 key。
  2. **GraphRAG**：用这些 id 在图里取 1～2 跳子图，生成「相关方案 + 型号 + 参数 + 信号链」的短文，append 到 `expert_cases_text`。
- 这样既不替换现有 RAG，又能在「方案设计前」引入图谱的结构化信息（型号-参数、方案-产品-信号链），提升参考质量。

### 6.3 实现顺序建议

- 先做「多跳扩展」：实现简单（从实体 id 遍历邻接），不依赖社区检测和社区摘要；
- 再视需要做「社区摘要」：需批量跑 LLM 生成摘要并建索引，适合图较大、希望用「高层语义」检索时。

---

## 七、实施顺序与依赖关系

| 步骤 | 内容 | 依赖 |
|------|------|------|
| 1 | 实现「从 complete_data.json 收集 product_link + 去重」脚本 | 无 |
| 2 | 用 crawl4ai 爬取每个 product_link，落盘为「url → markdown/html」 | 1 |
| 3 | 定义「你需要的参数」列表，写 LLM 抽取 prompt，产出 extracted_params | 2 |
| 4 | 写回 enriched 数据（enriched_products.json 或增强 complete_data） | 3 |
| 5 | 从 enriched 数据生成 RAG 文档列表，建 FAISS 索引（ADI 方案 RAG） | 4 |
| 6 | server_wb + generdatedata：接入 ADI RAG，合并 expert_cases_text | 5 |
| 7 | 设计图谱 schema，从 enriched + complete_data 建图（Neo4j/NetworkX） | 4 |
| 8 | 实现「从实体 id 多跳扩展 → 子图转文本」的 GraphRAG 模块 | 7 |
| 9 | 在检索流程中：向量 RAG 返回 id → GraphRAG 扩展 → 合并进 expert_cases_text | 6, 8 |

建议先做到步骤 6（ADI 向量 RAG 接入方案设计），验证参考效果后再做 7～9（图谱 + GraphRAG）。

---

## 八、目录与配置建议

```
fae_main/
├── analog_devices_data_test/          # 现有解决方案原始数据
├── enriched_solutions/                # 阶段 1 输出：增强后的方案 JSON（含 extracted_params）
│   └── by_solution/                  # 或按 solution 分子目录
├── adi_solution_index/               # 阶段 2：ADI RAG 的 FAISS 索引
├── adi_rag_documents.json            # 从 enriched 生成的 RAG 文档列表（供建索引）
├── crawl_from_html/
│   ├── qucik_crawl.py                # 现有 crawl4ai 单页爬取
│   ├── enrich_products_crawler.py    # 新增：批量 product_link 爬取
│   └── llm_extract_params.py         # 新增：LLM 参数抽取
├── rag_adi/                          # 新增：ADI 方案 RAG
│   ├── build_searchable_docs.py      # 从 enriched 生成 RAG 文档
│   ├── build_faiss_index.py          # 建 FAISS 索引
│   └── retriever.py                  # 检索接口，供 server_wb 调用
├── kg_adi/                           # 新增：知识图谱
│   ├── schema.py                     # 实体/关系定义
│   ├── build_graph.py                # 从 enriched + complete_data 建图
│   └── graph_rag.py                  # 多跳扩展 / 社区摘要
├── server_wb.py                      # 接入 ADI RAG + GraphRAG
└── docs/
    └── RAG_GraphRAG_Design.md        # 本文档
```

环境变量可扩展为：

- `RAG_DATA_PATH`：原有历史方案数据（不变）
- `RAG_DATA_PATH_ADI`：ADI RAG 文档来源（enriched 导出的 JSON）
- `RAG_INDEX_PATH_ADI`：`./adi_solution_index`
- `KG_PATH` 或 `NEO4J_URI`：图存储路径或 Neo4j 连接

---

## 九、小结

- **阶段 1**：用现有 solution JSON 里的 `product_link`，crawl4ai 爬取 → LLM 抽参 → 得到「带参数的型号」并写回 enriched 数据。
- **阶段 2**：用 enriched 数据构造文档并建向量索引，在 `/generate_all` 的 system_gen 前做 ADI 方案 RAG 检索，与现有历史方案 RAG 合并后注入 prompt。
- **阶段 3**：用 enriched + complete_data 建知识图谱（Solution / Product / Parameter / SignalChain 等），便于后续 GraphRAG。
- **阶段 4**：在检索时用图做多跳扩展（或社区摘要），把子图/路径描述并入 `expert_cases_text`，实现「RAG + GraphRAG」双路参考。

按上述顺序实现，即可在「方案设计前」先引入 RAG 作为方案设计参考，再在 RAG 基础上引入知识图谱和 GraphRAG，并与现有项目无缝对接。
