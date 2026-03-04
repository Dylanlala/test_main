# 专家知识库：用于用户需求分析时的参考设计

## 一、整体数据流

```
analog_devices_data_test / analog_test1（方案目录）
├── complete_data.json          # 方案页信息、产品列表、信号链元数据
├── enriched_products.json      # 可选：LLM 抽取的产品参数
└── signal_chain_descriptions.json  # 信号链「图转文」描述（你提供的 BMS 等）
        ↓
  run_rag_build.py（Stage 2）
        ↓
  adi_rag_documents.json + FAISS 索引  ← 文档里已含「方案概述 + 产品 + 信号链描述」
        ↓
  run_kg_build.py（Stage 3）
        ↓
  Neo4j：Solution、Product、Parameter、Category、**SignalChain**
        ↓
  用户需求（intention）→ 统一检索（retriever_unified）
        → 向量 RAG 召回方案文档（含信号链文字）
        → GraphRAG 从 solution_id 扩展子图（含 SignalChain 节点）
        → 拼成 expert_cases_text 注入下游（system_gen / 需求分析 LLM）
```

信号链图转文（如你提供的 BMS 框图描述）已接入三条线：

1. **RAG 文档**：`build_docs.py` 会读每个方案下的 `signal_chain_descriptions.json`，把「信号链【名称】：描述」拼进该方案的 doc，建索引后用户问「动力电池 BMS 架构」「车载充电 VCU」等都能命中。
2. **知识图谱**：`build_graph.py` 会为每条链建 `SignalChain` 节点（chain_id、list_name、description、image_url），并建 `Solution -[:HAS_SIGNAL_CHAIN]-> SignalChain`。
3. **GraphRAG**：`expand_from_solution_ids` 多跳扩展时已包含 Solution 连出去的 SignalChain，子图文本里会带上信号链的 list_name、description 等，供 LLM 参考。

---

## 二、你手里的内容怎么用

### 1. 已有 eVTOL BMS 图转文

- 已在 **analog_devices_data_test/eVTOL_BMS和电源** 和 **analog_test1/eVTOL_BMS和电源** 下写好 `signal_chain_descriptions.json`，内容即你提供的「新能源汽车动力电池系统功能架构框图」描述。
- 其他方案的信号链：对每条链的图片调豆包视觉 API，从 Response 里取出 `output_text` 的 `text`，按同样格式追加到该方案目录下的 `signal_chain_descriptions.json` 的 `chains` 数组即可。

### 2. 用 analog_test1 做专家库数据源（可选）

- 若希望**仅用** analog_test1 建 RAG/图谱，可在运行前改配置，让数据根指向 analog_test1：
  - 环境变量：`ANALOG_DATA_ROOT` 指向 `.../analog_test1`；
  - 或临时修改 `config.py` 里 `ANALOG_DATA_ROOT`。
- 然后执行：
  - `run_rag_build.py`（会读 analog_test1 下各方案 + 各方案下的 signal_chain_descriptions.json）
  - `run_kg_build.py`（会写 Neo4j，含 SignalChain）
- 若用默认的 `analog_devices_data_test`，则无需改配置，直接跑上述两个脚本即可。

### 3. 用户需求分析时的参考设计流程

- **入口**：用户输入「需求描述」（intention），例如：「我们要做 eVTOL 的电池管理系统，需要和整车 VCU 通信、支持车载充电」。
- **检索**：  
  - 调用 `UnifiedADIRetriever.retrieve_for_intention(intention, top_k=5)`。  
  - 内部先做**向量 RAG**：用 intention 查 FAISS，召回 top_k 条方案文档（文档里已含 eVTOL BMS 的方案概述 + 产品 + **信号链描述**，因此「BMS」「VCU」「车载充电」等会命中）。  
  - 再根据召回的 metadata 里的 solution_id 做 **GraphRAG 扩展**：在 Neo4j 里从这些 solution 多跳展开，拿到 Product、Parameter、Category、**SignalChain** 等节点，转成一段子图文本。  
- **输出**：`retrieve_for_intention` 返回的是一段 **expert_cases_text**（方案摘要 + 产品与参数 + 信号链与系统架构描述 + 知识图谱扩展），可直接作为「参考设计」注入到：
  - 需求分析 / 方案生成的 system prompt，或  
  - `generdatedata` / `server_wb` 里做选型、写白皮书时的上下文。

这样，用户需求分析时既能参考「方案级」描述，也能参考「信号链级」的框图语义（如 BMS 的 BMC、Cell Monitor、HV DC/DC、VCU 等），形成完整的专家知识库参考。

---

## 三、建议操作顺序

| 步骤 | 操作 | 说明 |
|------|------|------|
| 1 | 为其他方案补全 `signal_chain_descriptions.json` | 对每条有图的 signal_chain 调视觉 API，取 output_text 写入对应方案目录。 |
| 2 | 执行 RAG 构建 | `python adi_rag_pipeline/run_rag_build.py`（若用 analog_test1 则先设 `ANALOG_DATA_ROOT`）。 |
| 3 | 执行知识图谱构建 | `python adi_rag_pipeline/run_kg_build.py`（需 Neo4j 已起）。 |
| 4 | 在需求分析/生成里调用统一检索 | 使用 `retriever_unified.create_unified_retriever()`，再 `retrieve_for_intention(用户需求)`，将返回的 expert_cases_text 作为参考设计注入下游 LLM。 |

---

## 四、小结

- **RAG**：信号链图转文进入方案文档 → 用户问 BMS、车载充电、VCU、Cell Monitor 等都能被检索到。  
- **知识图谱**：SignalChain 节点 + HAS_SIGNAL_CHAIN 关系 → 和图上的 Solution、Product 一起参与扩展。  
- **GraphRAG**：扩展时已包含 SignalChain → 专家知识库既含「方案+产品」也含「信号链架构描述」。  
- **用户需求分析**：用 intention 做一次 `retrieve_for_intention`，得到的 expert_cases_text 即为当前管线下的「参考设计」片段，可直接用于需求分析或方案生成的上下文。
