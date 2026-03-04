# 信号链 RAG（stage2_rag_build）

从「方案 + 信号链描述 + 器件↔CSV 映射」构建 RAG，用于：根据用户需求检索最匹配的参考方案，并返回**方案 + 器件组成 + 电路设计描述 + 器件→型号参考**。

## 数据来源

- `complete_data.json`：方案元信息、产品列表、信号链列表（chain_id、list_name、signal_chain_hotspots）
- `signal_chain_mapping_for_rag.json`：每条链的 description_file、mapping_content、csv_files_for_chain
- `signal_chain_descriptions/*.txt`：图转文描述（器件列表、信号流向、应用场景）；写入 RAG 前会做规范截取（仅保留 ### 1～### 3）

## Chunk 设计

- **方案级**：每个 solution 一条，含方案名、关键词、描述、概述、产品列表、本方案信号链列表（chain_id + list_name）
- **信号链级**：每条链一条，含 chain_id、list_name、描述正文、器件↔CSV 映射表、本链 CSV 文件列表

## 用法

```bash
# 在项目根 fae_main 下执行

# 一键：生成文档 + 建 FAISS 索引（默认数据根 analog_test1）
python adi_rag_pipeline/stage2_rag_build/run_build.py

# 仅生成文档
python adi_rag_pipeline/stage2_rag_build/run_build.py --docs-only

# 仅建索引（需已有 rag_documents.json）
python adi_rag_pipeline/stage2_rag_build/run_build.py --index-only

# 指定数据根与输出路径
python adi_rag_pipeline/stage2_rag_build/run_build.py --data-root /path/to/analog_test1 --docs ./my_docs.json --index ./my_index
```

## 检索

```python
from adi_rag_pipeline.stage2_rag_build import create_retriever

retriever = create_retriever()
if retriever:
    results = retriever.retrieve("雷达领域精密SMU/PMU半导体参数测量信号链", top_k=5)
    for r in results:
        print(r["metadata"].get("solution_id"), r["metadata"].get("chain_id"), r["metadata"].get("list_name"))
        print(r["text"][:300], "...")
```

## 输出路径（config）

- 文档列表：`adi_rag_pipeline/stage2_rag_build/rag_documents.json`
- FAISS 索引：`adi_rag_pipeline/stage2_rag_build/rag_index/`

## 依赖

与 adi_rag_pipeline 一致：`langchain_community`、`faiss-cpu`；Embedding 使用 config 中的 `EMBEDDING_MODEL_NAME`、`EMBEDDING_CACHE`。
