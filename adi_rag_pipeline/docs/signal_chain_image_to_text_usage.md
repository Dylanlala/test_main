# 信号链「图转文」内容怎么用

## 从 Responses API 里取出「最终描述」

你用的是 `client.responses.create()`，返回的 `Response` 里：

- **最终可读描述**（给 RAG/白皮书用）：在 `response.output` 里找到 `type='message'` 且 `role='assistant'` 的项，其 `content` 里 `type='output_text'` 的 `text` 即为整段结构化描述。
- **推理过程**（可选）：`type='reasoning'` 的项里 `summary[].text` 是模型的逐步分析，可用于调试或深度展示。

示例（伪代码）：

```python
# response = client.responses.create(...)
for item in response.output or []:
    if getattr(item, "type", None) == "message" and getattr(item, "content", None):
        for part in item.content:
            if getattr(part, "type", None) == "output_text" and hasattr(part, "text"):
                final_description = part.text  # 即你要存、要喂给 RAG 的文本
                break
```

若用 `ark_image_to_text.py` 那种 Chat Completions 接口，则直接取 `response.choices[0].message.content` 即可。

---

## 你拿到的内容是什么

豆包 Responses API 返回里有两块可直接用：

| 部分 | 位置 | 用途 |
|------|------|------|
| **推理过程** | `output[].summary[].text`（reasoning） | 模型如何读图、分块、核对，适合做调试或给高级用户看 |
| **最终描述** | `output[].content[].text`（message content） | 已整理好的「整体定位 + 左侧/核心/右侧/支撑」结构化文字，**适合入库、检索、给下游 LLM 用** |

当前这条是「基于 SHARC 的车载高端音频 ECU 框图」：Head Unit 四种接入、SHARC 外设、右侧 ANC/麦克风/A2B/放音等通路、电源与软件支撑。可直接当「该信号链的语义描述」使用。

---

## 1. 写入数据：每个方案下为每条链存一份描述

- **存哪里**：每个 solution 目录下增加一份 `signal_chain_descriptions.json`（或按链存成 `signal_chains/<chain_id>_description.txt`）。
- **内容**：`chain_id` → 对应图转文的 **最终描述**（即 `output[].content[].text`），可选带 `list_name`、`source_image_url`。
- **谁写**：在 stage1_enrich 里加一步：遍历 `complete_data.json` 的 `signal_chains.chains`，对每条链的 `image_info.img_url`（或本地图）调视觉 API，解析 Responses 取 `content[].text`，写回上述文件。

这样 RAG/图谱/白皮书都从「已有文件」读，无需每次看图。

---

## 2. 用于 RAG 检索（推荐）

- **现状**：`stage2_rag/build_docs.py` 只拼了 `page_info` + 产品/参数，**没有**信号链文字，用户搜「车载主动降噪」「A2B 麦克风」时很难命中「哪条信号链在讲这个」。
- **用法**：在 `build_doc_for_solution()` 里，若存在 `signal_chain_descriptions.json`，则把「信号链名称 + 该链描述」拼进同一 solution 的 `text`（例如加一段「信号链：…」）。
- **效果**：向量检索时既能按方案概述、产品型号匹配，也能按框图语义匹配（例如「远程调谐」「ANC/RNC」「Class D 功放」），返回的方案文档里已经包含对应信号链说明，可直接给 LLM 做参考。

---

## 3. 用于知识图谱 / GraphRAG

- **现状**：Neo4j schema 里没有 SignalChain 节点，只有 Solution / Product / Parameter / Category。
- **用法**：若后续加「SignalChain」节点，可把图转文描述作为该节点的 `description` 或 `summary` 属性；GraphRAG 扩展时不仅能走 Solution→Product，还能走 Solution→SignalChain，把「这条链在讲什么」一并带给 LLM。

---

## 4. 用于白皮书 / 方案书生成

- **现状**：`whitepdf` 等用 intention + system_block + BOM + description 生成正文，没有「系统框图在说什么」的文本。
- **用法**：在生成「系统架构设计」等章节时，把当前方案下相关信号链的图转文描述作为 **参考段落** 注入 prompt（例如放在「方案参考」里），让 LLM 按框图语义写架构描述、接口关系，而不是纯编，减少偏差。

---

## 5. 和产品列表做关联（进阶）

- 描述里会出现器件/接口名（如 SHARC、A2B、ADC、DAC、Class D、ANC/RNC）。可以：
  - 用关键词或简单 NER 从描述里抽「提到的型号/模块名」；
  - 和本方案 `hardware_products` / `evaluation_products` 的 `model`、`description` 做匹配，给 `signal_chain_hotspots` 或单独一张「链 ↔ 产品」关联表，用于「点框图某块 → 跳转到产品页」或推荐选型。

---

## 6. 推荐落地顺序

1. **先落存储**：在 stage1_enrich 里对每条有图的 signal_chain 调视觉 API，把「最终描述」写入该 solution 下的 `signal_chain_descriptions.json`（结构见下）。
2. **再接 RAG**：在 `build_docs.py` 里读该文件，把信号链描述拼进 doc `text`，重跑 `run_rag_build.py`，检索效果即可提升。
3. 若要做图谱或白皮书增强，再在 Neo4j 建链节点、在 whitepdf 的 prompt 里注入描述。

---

## 建议的数据格式示例

每个 solution 目录下 `signal_chain_descriptions.json`：

```json
{
  "updated_at": "2025-03-01T12:00:00",
  "chains": [
    {
      "chain_id": "0519",
      "list_name": "远程信息处理紧急呼叫(E-Call)箱",
      "image_url": "https://www.analog.com/packages/isc/v2824/zh/isc-0519.png",
      "description": "（图转文的最终描述，即 response output content 的 text）"
    }
  ]
}
```

`build_docs.py` 中只需：若存在该文件，则遍历 `chains`，拼成一段「信号链 [list_name]：description」，追加到当前 solution 的 `text_parts` 即可。
