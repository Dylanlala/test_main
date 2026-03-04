# analog_rag 配置：与 lina_code_new 一致的 RAG 方案检索（基于 analog_test1）
import os

# 方案库根目录（包含多个解决方案文件夹，每个文件夹有 complete_data.json）
ANALOG_TEST1_ROOT = os.path.join(os.path.dirname(os.path.dirname(__file__)), "analog_test1")

# 关键词提取结果目录（每个方案一个 JSON，含四类关键词）
KEYWORD_EXTRACTION_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "analog_rag_output", "keyword_extraction")

# 向量与元数据输出目录（与 lina 一致：keyword_embeddings.npy + keyword_metadata.csv）
EMBEDDINGS_OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "analog_rag_output", "embeddings")

# 四类关键词（与 lina_code_new 完全一致）
CATEGORY_ORDER = ["解决方案类型", "技术类型", "核心组件", "性能指标"]
CATEGORY_WEIGHTS = {
    "解决方案类型": 0.35,
    "技术类型": 0.30,
    "核心组件": 0.20,
    "性能指标": 0.15,
}

# 检索默认参数
DEFAULT_TOP_K = 5
DEFAULT_SIMILARITY_THRESHOLD = 0.4
DEFAULT_SCORE_THRESHOLD = 0.3
DEFAULT_MAX_CANDIDATES = 100
