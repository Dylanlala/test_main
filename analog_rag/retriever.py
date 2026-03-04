# 与 lina_code_new 一致的检索逻辑：四类关键词 + FAISS + 加权得分；对外接口供 generdatedata 接入
import os
import re
import json
import numpy as np
import pandas as pd
import faiss
from collections import defaultdict
from typing import List, Dict, Any, Optional, Set
from .config import (
    EMBEDDINGS_OUTPUT_DIR,
    CATEGORY_ORDER,
    CATEGORY_WEIGHTS,
    DEFAULT_TOP_K,
    DEFAULT_SIMILARITY_THRESHOLD,
    DEFAULT_SCORE_THRESHOLD,
    DEFAULT_MAX_CANDIDATES,
)

# 用户查询关键词提取 prompt（与 lina scheme_search 一致）
QUERY_KEYWORD_PROMPT = """你是一名专业的电子工程师，负责分析技术方案需求并将其核心信息结构化。请严格遵循以下指令。

# 任务：
请从"技术方案需求"中提取所有相关关键词，并将它们分配到以下四个固定分类中。每个关键词只分配到一个分类。
1. 解决方案类型：该技术方案所实现的具体功能或解决的特定工程问题。
2. 技术类型：方案中采用的核心技术、方法、架构或功能。
3. 核心组件：方案中提及的具体物理实体或芯片型号、名称。
4. 性能指标：方案的关键电气参数、性能特征和量化指标。

# 输出格式：
请严格输出一个JSON对象，且只包含一个名为`keywords`的键，值为对象，键为分类名称，值为该分类下的关键词数组。
例如 {{"keywords": {{"解决方案类型": ["xxx"], "技术类型": [], "核心组件": [], "性能指标": []}}}}

# 技术方案需求：
"{query_text}"
"""


def _parse_keywords(content: str) -> Dict[str, list]:
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL)
    content = content.strip()
    default = {"解决方案类型": [], "技术类型": [], "核心组件": [], "性能指标": []}
    try:
        data = json.loads(content)
        if "keywords" in data and isinstance(data["keywords"], dict):
            return {k: v if isinstance(v, list) else [] for k, v in data["keywords"].items()}
    except json.JSONDecodeError:
        pass
    start, end = content.find("{"), content.rfind("}") + 1
    if start >= 0 and end > start:
        try:
            data = json.loads(content[start:end])
            if "keywords" in data and isinstance(data["keywords"], dict):
                return {k: v if isinstance(v, list) else [] for k, v in data["keywords"].items()}
        except json.JSONDecodeError:
            pass
    return default


class AnalogCategoryOrderedFAISSSearch:
    """与 lina 一致的按类别加权 FAISS 检索。"""
    def __init__(self, embeddings_path: str, metadata_path: str):
        self.kb_embeddings = np.load(embeddings_path)
        self.kb_metadata = pd.read_csv(metadata_path)
        self.dimension = self.kb_embeddings.shape[1]
        self.category_order = CATEGORY_ORDER
        self.category_weights = CATEGORY_WEIGHTS
        self.scheme_to_indices = self._build_scheme_indices()
        self.scheme_category_indices = self._precompute_category_indices()
        embeddings_norm = self.kb_embeddings.copy()
        faiss.normalize_L2(embeddings_norm)
        self.index = faiss.IndexFlatIP(self.dimension)
        self.index.add(embeddings_norm)

    def _build_scheme_indices(self) -> Dict[str, List[int]]:
        out = {}
        for idx, row in self.kb_metadata.iterrows():
            sid = row["scheme_id"]
            if sid not in out:
                out[sid] = []
            out[sid].append(idx)
        return out

    def _precompute_category_indices(self) -> Dict[str, Dict[str, List[int]]]:
        out = {}
        for cat in self.category_order:
            out[cat] = {}
            for sid, indices in self.scheme_to_indices.items():
                sub = [i for i in indices if self.kb_metadata.iloc[i]["category"] == cat]
                if sub:
                    out[cat][sid] = sub
        return out

    def compute_category_score(
        self,
        query_embeddings: np.ndarray,
        query_categories: List[str],
        target_category: str,
        scheme_id: str,
    ) -> float:
        q_idx = [i for i, c in enumerate(query_categories) if c == target_category]
        if not q_idx:
            return 0.0
        if scheme_id not in self.scheme_category_indices.get(target_category, {}):
            return 0.0
        s_idx = self.scheme_category_indices[target_category][scheme_id]
        q_emb = query_embeddings[q_idx].astype(np.float32)
        s_emb = self.kb_embeddings[s_idx].astype(np.float32)
        faiss.normalize_L2(q_emb)
        faiss.normalize_L2(s_emb)
        sim = np.dot(q_emb, s_emb.T)
        max_per_query = np.max(sim, axis=1)
        return float(np.mean(max_per_query))

    def search(
        self,
        query_embeddings: np.ndarray,
        query_categories: List[str],
        similarity_threshold: float = 0.4,
        score_threshold: float = 0.3,
        max_candidates: int = 100,
    ) -> List[Dict[str, Any]]:
        candidate_schemes = set(self.scheme_to_indices.keys())
        scheme_category_scores = defaultdict(dict)
        solution_schemes = set()
        for sid in candidate_schemes:
            score = self.compute_category_score(
                query_embeddings, query_categories, "解决方案类型", sid
            )
            if score >= similarity_threshold:
                solution_schemes.add(sid)
                scheme_category_scores[sid]["解决方案类型"] = score
        if len(solution_schemes) > max_candidates:
            scored = sorted(
                [(sid, scheme_category_scores[sid].get("解决方案类型", 0)) for sid in solution_schemes],
                key=lambda x: x[1],
                reverse=True,
            )
            solution_schemes = set(sid for sid, _ in scored[:max_candidates])
            scheme_category_scores = {k: v for k, v in scheme_category_scores.items() if k in solution_schemes}
        for cat in ["技术类型", "核心组件", "性能指标"]:
            for sid in solution_schemes:
                sc = self.compute_category_score(query_embeddings, query_categories, cat, sid)
                scheme_category_scores[sid][cat] = sc
        present = set(query_categories)
        total_w = sum(self.category_weights.get(c, 0.1) for c in present if c in self.category_weights)
        if total_w <= 0:
            total_w = 1.0
        weighted = {}
        for sid, scores in scheme_category_scores.items():
            w = sum(scores.get(c, 0) * self.category_weights.get(c, 0.1) for c in present)
            weighted[sid] = w / total_w
        sorted_schemes = sorted(weighted.items(), key=lambda x: x[1], reverse=True)
        filtered = [(sid, sc) for sid, sc in sorted_schemes if sc >= score_threshold]
        results = []
        for sid, score in filtered:
            results.append({
                "scheme_id": sid,
                "weighted_score": score,
                "category_scores": dict(scheme_category_scores.get(sid, {})),
            })
        return results


class AnalogSchemeRAGRetriever:
    """
    供 generdatedata 使用的 RAG 检索器：与 lina 一致的四类关键词 + FAISS。
    接口：retrieve_similar_cases(query, top_k, similarity_threshold), format_cases_for_llm(cases, max_tokens).
    """
    def __init__(
        self,
        embeddings_path: str = None,
        metadata_path: str = None,
        scheme_details_path: str = None,
        client=None,
        model: str = "bot-20250618131857-l9ffp",
        embedding_model_name: str = "aspire/acge_text_embedding",
    ):
        out_dir = embeddings_path and os.path.dirname(embeddings_path) or EMBEDDINGS_OUTPUT_DIR
        self.embeddings_path = embeddings_path or os.path.join(out_dir, "keyword_embeddings.npy")
        self.metadata_path = metadata_path or os.path.join(out_dir, "keyword_metadata.csv")
        self.scheme_details_path = scheme_details_path or os.path.join(out_dir, "scheme_details.json")
        self.client = client
        self.model = model
        self._embedding_model = None
        self._embedding_model_name = embedding_model_name
        self._search_engine = None
        self._scheme_details = {}
        self._load()

    def _load(self):
        if not os.path.isfile(self.embeddings_path) or not os.path.isfile(self.metadata_path):
            return
        self._search_engine = AnalogCategoryOrderedFAISSSearch(
            self.embeddings_path,
            self.metadata_path,
        )
        if os.path.isfile(self.scheme_details_path):
            try:
                with open(self.scheme_details_path, "r", encoding="utf-8") as f:
                    self._scheme_details = json.load(f)
            except Exception:
                pass

    def _get_embedding_model(self):
        if self._embedding_model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._embedding_model = SentenceTransformer(
                    self._embedding_model_name,
                    local_files_only=True,
                )
            except Exception as e:
                print(f"Analog RAG: Embedding 模型加载失败: {e}")
        return self._embedding_model

    def _extract_query_keywords(self, query: str) -> Dict[str, list]:
        if not self.client or not query.strip():
            return {"解决方案类型": [query.strip()] if query.strip() else [], "技术类型": [], "核心组件": [], "性能指标": []}
        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": QUERY_KEYWORD_PROMPT.format(query_text=query[:8000])}],
                temperature=0.2,
                max_tokens=1024,
            )
            content = (resp.choices[0].message.content or "").strip()
            return _parse_keywords(content)
        except Exception as e:
            print(f"Analog RAG: 查询关键词提取失败: {e}")
            return {"解决方案类型": [query[:500]], "技术类型": [], "核心组件": [], "性能指标": []}

    def _embed_keywords(self, keywords_dict: Dict[str, list]) -> tuple:
        model = self._get_embedding_model()
        if model is None:
            return None, [], []
        all_kw, all_cat = [], []
        for cat, kws in keywords_dict.items():
            for kw in (kws or []):
                if kw and isinstance(kw, str) and kw.strip():
                    all_kw.append(kw.strip())
                    all_cat.append(cat)
        if not all_kw:
            return None, [], []
        emb = model.encode(all_kw, show_progress_bar=False)
        return np.array(emb, dtype=np.float32), all_cat, all_kw

    def retrieve_similar_cases(
        self,
        query: str,
        top_k: int = None,
        similarity_threshold: float = None,
        score_threshold: float = None,
    ) -> List[Dict[str, Any]]:
        top_k = top_k if top_k is not None else DEFAULT_TOP_K
        similarity_threshold = similarity_threshold if similarity_threshold is not None else DEFAULT_SIMILARITY_THRESHOLD
        score_threshold = score_threshold if score_threshold is not None else DEFAULT_SCORE_THRESHOLD

        if self._search_engine is None:
            return []
        keywords_dict = self._extract_query_keywords(query)
        query_emb, query_cats, _ = self._embed_keywords(keywords_dict)
        if query_emb is None:
            return []
        raw = self._search_engine.search(
            query_emb,
            query_cats,
            similarity_threshold=similarity_threshold,
            score_threshold=score_threshold,
            max_candidates=max(top_k * 3, 50),
        )
        # 取 top_k，并补全 title/description/characteristic
        cases = []
        for r in raw[:top_k]:
            sid = r["scheme_id"]
            detail = self._scheme_details.get(sid, {})
            cases.append({
                "scheme_id": sid,
                "weighted_score": r["weighted_score"],
                "category_scores": r.get("category_scores", {}),
                "title": detail.get("title") or sid,
                "description": detail.get("description") or "",
                "characteristic": detail.get("characteristic") or "",
                "scheme_name": detail.get("scheme_name") or sid,
                "signal_chain_parts": detail.get("signal_chain_parts") or "",
            })
        return cases

    def format_cases_for_llm(
        self,
        similar_cases: List[Dict[str, Any]],
        max_tokens: int = 800,
    ) -> str:
        if not similar_cases:
            return "暂无历史参考方案。"
        parts = []
        approx = 0
        for i, c in enumerate(similar_cases):
            if approx >= max_tokens * 2:
                break
            title = c.get("title") or c.get("scheme_id", "")
            desc = (c.get("description") or "")[:500]
            char = (c.get("characteristic") or "")[:300]
            signal_parts = (c.get("signal_chain_parts") or "")[:600]
            block = f"【参考方案 {i+1}】{title}\n描述: {desc}\n特性: {char}"
            if signal_parts:
                block += f"\n信号链模块与可选型号参数: {signal_parts}"
            parts.append(block)
            approx += len(block)
        return "\n\n".join(parts)


def create_analog_rag_retriever(
    embeddings_dir: str = None,
    client=None,
    model: str = "bot-20250618131857-l9ffp",
) -> Optional[AnalogSchemeRAGRetriever]:
    """工厂函数：创建基于 analog_rag_output 的检索器，供 server_wb 传入 generdatedata。"""
    embeddings_dir = embeddings_dir or EMBEDDINGS_OUTPUT_DIR
    emb_path = os.path.join(embeddings_dir, "keyword_embeddings.npy")
    meta_path = os.path.join(embeddings_dir, "keyword_metadata.csv")
    if not os.path.isfile(emb_path) or not os.path.isfile(meta_path):
        print("Analog RAG: 未找到 keyword_embeddings.npy 或 keyword_metadata.csv，请先运行 build 流程")
        return None
    return AnalogSchemeRAGRetriever(
        embeddings_path=emb_path,
        metadata_path=meta_path,
        scheme_details_path=os.path.join(embeddings_dir, "scheme_details.json"),
        client=client,
        model=model,
    )
