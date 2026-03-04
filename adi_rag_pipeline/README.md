# ADI RAG Pipeline

从 `analog_devices_data_test` 的解决方案 JSON 出发：用 crawl4ai 爬取产品页、LLM 抽取参数，写回各 solution 下的 `enriched_products.json`；再构建向量 RAG（FAISS）与 Neo4j 知识图谱（不包含 SignalChain），并提供 GraphRAG 多跳扩展，供方案设计前检索参考。

## 目录结构

```
adi_rag_pipeline/
├── config.py                 # 路径与 Neo4j/LLM 配置
├── stage1_enrich/            # 数据增强
│   ├── collect_links.py      # 从 complete_data.json 收集 product_link
│   ├── crawl_products.py     # crawl4ai 批量爬取并缓存
│   ├── llm_extract_params.py # LLM 抽取参数
│   └── write_enriched.py     # 写回 enriched_products.json
├── stage2_rag/               # 向量 RAG
│   ├── build_docs.py         # 构建 RAG 文档列表
│   ├── build_index.py        # FAISS 索引
│   └── retriever.py          # 检索接口
├── stage3_kg/                # Neo4j 知识图谱（无 SignalChain）
│   ├── schema.py
│   └── build_graph.py
├── stage4_graph_rag/         # GraphRAG 多跳扩展
│   └── graph_rag.py
├── retriever_unified.py      # 统一检索（RAG + GraphRAG）
├── run_enrich.py             # 一键：爬取 + 抽取 + 写回
├── run_rag_build.py          # 一键：文档 + FAISS 索引
├── run_kg_build.py           # 一键：Neo4j 建图
└── README.md
```

## 依赖

- 项目根目录 `fae_main` 下已有：`analog_devices_data_test/`、`static/key1.txt`（LLM API Key）
- Python 包：`crawl4ai`、`openai`、`langchain_community`、`faiss-cpu`、`neo4j`、`json_repair`
- Neo4j 服务（Stage 3/4）：默认 `bolt://localhost:7687`，可通过环境变量 `NEO4J_URI`、`NEO4J_USER`、`NEO4J_PASSWORD` 配置

## 运行顺序

在 **fae_main** 目录下执行（或确保 `fae_main` 在 `PYTHONPATH` 中）：

1. **Stage 1 - 数据增强**  
   ```bash
   python adi_rag_pipeline/run_enrich.py
   ```  
   会：收集所有 product_link → 用 crawl4ai 爬取并写入 `adi_rag_pipeline/cache/crawl/` → 用 LLM 抽取参数 → 在每个 solution 目录下生成 `enriched_products.json`。

2. **Stage 2 - RAG**  
   ```bash
   python adi_rag_pipeline/run_rag_build.py
   ```  
   会：根据各 solution 的 complete_data + enriched_products 生成 `adi_rag_documents.json`，并构建 FAISS 索引到 `adi_rag_pipeline/adi_solution_index/`。

3. **Stage 3 - 知识图谱**  
   先启动 Neo4j，再执行：  
   ```bash
   export NEO4J_URI=bolt://localhost:7687 NEO4J_USER=neo4j NEO4J_PASSWORD=你的密码
   python adi_rag_pipeline/run_kg_build.py
   ```  
   会：清空图后，从 complete_data + enriched_products 写入 Solution、Product、Parameter、Category 及关系（不包含 SignalChain）。

## 接入方案设计流程

在 `server_wb.py` 中：

1. 初始化统一检索器（与现有 embedding 复用）：  
   ```python
   from adi_rag_pipeline.retriever_unified import create_unified_retriever
   adi_retriever = create_unified_retriever(embedding_model=embeddingmodel, use_graph_rag=True)
   ```
2. 在 `generate_all` 中，调用 `system_gen` 前：  
   ```python
   expert_cases_adi = adi_retriever.retrieve_for_intention(intention, top_k=5)
   # 与原有 expert_cases_text_legacy 合并后传入 noBaseGenerator 或 prompt
   ```

## 配置说明

- **config.py**：`ANALOG_DATA_ROOT`、`RAG_INDEX_PATH`、`NEO4J_*`、`LLM_*`、`EMBEDDING_*`、`CRAWL_CACHE_DIR` 等。
- **enriched_products.json**：每个 solution 目录下一份，格式为 `[ { "model", "product_link", "category", "description", "extracted_params" }, ... ]`。

## SignalChain 与信号链图→CSV 映射（测试）

- **测试数据**：使用 `analog_test1` 目录（与 config 中 `ANALOG_DATA_ROOT` 一致）。推荐先用方案 **下一代气象雷达**（含 `exports_signal_chain_csv` 下多条链的选型表）。
- **脚本**：`stage1_signal_to_solution/signal_chain_image_to_csv_mapping.py`  
  - Step1：豆包视觉读信号链图片，输出**器件列表 + 信号流向**，写入方案目录下 `signal_chain_descriptions/*_description.txt`。  
  - Step2：LLM 根据描述与 `exports_signal_chain_csv` 文件名建立**器件↔CSV 映射**，输出 `signal_chain_{chain_id}_description_to_csv_mapping.md` 与 `signal_chain_mapping_for_rag.json`，供后续 RAG 构建使用。  
- **运行示例**（在项目根或 `adi_rag_pipeline/stage1_signal_to_solution` 下）：  
  ```bash
  python adi_rag_pipeline/stage1_signal_to_solution/signal_chain_image_to_csv_mapping.py "下一代气象雷达"
  ```  
  若方案下 `signal_chains` 为空，脚本会尝试从 `complete_data.json` 的 `image_info.img_url` 下载图片后再执行 Step1。

本 pipeline 其余部分暂不包含 SignalChain 节点与关系；SignalChain 的图仅作后续从图中提取有用信息用于设计，当前只做 RAG + 产品/参数图谱。
