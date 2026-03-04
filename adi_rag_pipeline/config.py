# ADI RAG Pipeline 配置
# 数据路径相对于项目根目录 fae_main
import os

# 项目根目录（adi_rag_pipeline 的上一级）
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 阶段 0：原始解决方案数据
ANALOG_DATA_ROOT = os.path.join(PROJECT_ROOT, "analog_test1")

# 阶段 1：爬取缓存与输出
CRAWL_CACHE_DIR = os.path.join(PROJECT_ROOT, "adi_rag_pipeline", "cache", "crawl")
# enriched_products.json 写回在每个 solution 目录下，此处仅做说明
ENRICHED_PRODUCTS_FILENAME = "enriched_products.json"

# 阶段 2：RAG
RAG_DOCS_PATH = os.path.join(PROJECT_ROOT, "adi_rag_pipeline", "adi_rag_documents.json")
RAG_INDEX_PATH = os.path.join(PROJECT_ROOT, "adi_rag_pipeline", "adi_solution_index")

# 阶段 2 信号链 RAG（stage2_rag_build：方案+信号链描述+器件↔CSV 映射）
RAG_BUILD_DOCS_PATH = os.path.join(PROJECT_ROOT, "adi_rag_pipeline", "stage2_rag_build", "rag_documents.json")
RAG_BUILD_INDEX_PATH = os.path.join(PROJECT_ROOT, "adi_rag_pipeline", "stage2_rag_build", "rag_index")

# 阶段 3：Neo4j（不包含 SignalChain）
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")

# LLM：与主项目一致，豆包 Ark
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3/bots")
LLM_API_KEY_PATH = os.path.join(PROJECT_ROOT, "static", "key1.txt")
LLM_MODEL = os.getenv("LLM_MODEL", "bot-20250618131857-l9ffp")

# Step2 建立映射失败时的备用模型（默认 deepseek-v3-2-251201）。用 DeepSeek 时建议设 STEP2_FALLBACK_BASE_URL=https://api.deepseek.com 与 STEP2_FALLBACK_API_KEY
STEP2_FALLBACK_MODEL = os.getenv("STEP2_FALLBACK_MODEL", "deepseek-v3-2-251201")
STEP2_FALLBACK_BASE_URL = os.getenv("STEP2_FALLBACK_BASE_URL", "").strip()  # 若设则用该 endpoint，否则用主 endpoint 换 model
STEP2_FALLBACK_API_KEY = os.getenv("STEP2_FALLBACK_API_KEY", "").strip()   # 备用 endpoint 的 Key，空则用 LLM_API_KEY

# Embedding：与 server_wb 一致
EMBEDDING_MODEL_NAME = "../paraphrase-multilingual-MiniLM-L12-v2"
EMBEDDING_CACHE = os.getenv("EMBEDDING_CACHE", "/data/alg/fae/paraphrase-multilingual-MiniLM-L12-v2")

# 多模态/视觉模型（Step1 读图用）。若报 404 ModelNotOpen，需在 Ark 控制台开通该模型或改为已开通的模型 ID
VISION_MODEL = os.getenv("VISION_MODEL", "doubao-seed-2-0-pro-260215")
MAIN_API_KEY = os.getenv("MAIN_API_KEY", "88632c3b-7c51-4517-83a1-c77957720f11")

# 爬取限速（秒）
CRAWL_DELAY_MIN = 1.0
CRAWL_DELAY_MAX = 2.0

# LLM 抽取时页面内容最大字符（避免超长）
MAX_PAGE_CHARS_FOR_EXTRACT = 12000


def get_llm_api_key():
    if os.path.exists(LLM_API_KEY_PATH):
        with open(LLM_API_KEY_PATH, "r", encoding="utf-8") as f:
            return f.read().strip()
    return os.getenv("LLM_API_KEY", "")