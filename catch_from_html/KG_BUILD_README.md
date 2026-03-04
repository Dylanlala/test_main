# 知识图谱构建说明

管线 `kg_pipeline_from_complete_data.py` 跑完后，用本说明和 `kg_build.py` 把结果建成图并导出，供图数据库或 RAG 使用。

---

## 一、管线产出（output_kg/）

| 文件 | 用途 |
|------|------|
| `product_core_params_<timestamp>.json` | 产品节点：型号、核心参数、关键特性、应用、source_url |
| `solution_summaries_<timestamp>.json` | 方案节点：方案名、摘要、关键词、特性、优势、应用、hardware_components（含产品链接） |
| `product_links_*.json` / `crawled_products_*.json` | 中间数据，构建图时不需要 |
| `index_*.json` | 当次运行统计 |

---

## 二、图模型（本脚本采用的 schema）

- **节点**
  - **Solution**：一个方案一个节点  
    - `id`：方案目录名或方案名（唯一）  
    - `solution_name`, `solution_url`, `solution_summary`, `keywords`, `key_features`, `core_advantages`, `target_applications`
  - **Product**：一个产品页一个节点（按产品链接去重）  
    - `id`：产品页 URL（唯一）  
    - `model`, `title`, `category`, `description`, `source_url`, `core_params`, `key_features`, `applications`

- **边**
  - **Solution -[:CONTAINS_PRODUCT]-> Product**  
    - 属性：`web_category`（硬件产品/评估板/参考设计）、`category`、`model`

---

## 三、构建与导出（kg_build.py）

### 1. 默认：用最新一次管线结果

```bash
python kg_build.py
```

- 自动在 `output_kg/` 下找最新的 `product_core_params_*.json` 和 `solution_summaries_*.json`
- 在项目下生成 `kg_export/`，写入：
  - `nodes_solution_<ts>.csv` / `nodes_product_<ts>.csv`：节点表
  - `edges_contains_product_<ts>.csv`：方案-产品边表
  - `knowledge_graph_<ts>.json`：整图（节点+边+meta）
  - `neo4j_import_<ts>.cypher`：Neo4j 可执行脚本

### 2. 指定文件和目录

```bash
python kg_build.py \
  --output-dir /path/to/output_kg \
  --export-dir /path/to/kg_export \
  --product-file /path/to/product_core_params_20260212_002521.json \
  --solution-file /path/to/solution_summaries_20260212_002521.json
```

### 3. 只导出部分格式

```bash
python kg_build.py --no-csv    # 不生成 CSV
python kg_build.py --no-neo4j  # 不生成 Neo4j Cypher
```

---

## 四、后续怎么“用”这张图

### 方式 A：Neo4j 图数据库

1. 安装 [Neo4j](https://neo4j.com/download/)（Desktop 或 Server）。
2. 新建一个空库（或清空现有库）。
3. 在 Neo4j Browser 或 `cypher-shell` 中执行生成的 `neo4j_import_<ts>.cypher`。
4. 示例查询：
   - 某方案下有哪些产品：  
     `MATCH (s:Solution { id: '10BASE-T1S_E2B远程控制协议(RCP)' })-[:CONTAINS_PRODUCT]->(p:Product) RETURN p.model, p.source_url`
   - 某产品被哪些方案引用：  
     `MATCH (s:Solution)-[:CONTAINS_PRODUCT]->(p:Product { model: 'AD3300' }) RETURN s.solution_name, s.solution_url`
   - 按应用场景找方案：  
     `MATCH (s:Solution) WHERE s.target_applications IS NOT NULL AND s.solution_summary CONTAINS '汽车' RETURN s.solution_name, s.solution_summary`

### 方式 B：RAG / 向量检索

- 把 `knowledge_graph_<ts>.json` 里的 `solution_summary`、`key_features`、产品 `description`、`core_params` 等抽成文本块，写入向量库（如 Milvus、ES、或 LangChain 的 DocumentLoader）。
- 检索时：用户问“某场景用什么方案/芯片”，先向量检索到相关方案/产品，再根据需要查图（例如用 Neo4j）做“方案-产品”关系展开。

### 方式 C：仅用 CSV/Excel

- 用 `nodes_solution_*.csv`、`nodes_product_*.csv`、`edges_*.csv` 在 Excel 或 BI 里做分析、看方案-产品对应关系；或导入其他支持“节点表+边表”的图工具。

### 方式 D：Python 内存图（NetworkX 等）

- 读取 `knowledge_graph_<ts>.json`，用 NetworkX 建图后再做图算法、可视化或自定义导出：

```python
import json
import networkx as nx

with open("kg_export/knowledge_graph_xxx.json", "r", encoding="utf-8") as f:
    g = json.load(f)

G = nx.DiGraph()
for n in g["nodes"]["solution"]:
    G.add_node(n["id"], label="Solution", **n)
for n in g["nodes"]["product"]:
    G.add_node(n["id"], label="Product", **n)
for e in g["edges"]:
    G.add_edge(e["from_id"], e["to_id"], relation=e["relation"], **e)

# 例：某方案的所有产品
list(G.successors("10BASE-T1S_E2B远程控制协议(RCP)"))
```

---

## 五、小结

| 步骤 | 脚本/文件 | 说明 |
|------|------------|------|
| 1 | `kg_pipeline_from_complete_data.py` | 从 complete_data 爬产品、抽参数、生成方案 JSON，写入 `output_kg/` |
| 2 | `kg_build.py` | 读 `output_kg/` 最新结果，建「方案-产品」图，导出 CSV/JSON/Neo4j |
| 3 | 按需 | Neo4j 导入 Cypher / RAG 用 JSON / Excel 用 CSV / Python 用 JSON+NetworkX |

按上述顺序执行即可在管线完成后完成知识图谱构建与多种下游使用方式。
