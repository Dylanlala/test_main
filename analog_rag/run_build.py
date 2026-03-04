# 一键构建 analog RAG 索引：1）提取关键词（需 LLM） 2）向量化并保存 npy/csv/scheme_details
import os
import sys

# 将项目根目录加入 path，便于单独运行本脚本时 import
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def main():
    from openai import OpenAI
    from analog_rag.keyword_extractor import run_keyword_extraction
    from analog_rag.embed_keywords import run_embed
    from analog_rag.config import (
        ANALOG_TEST1_ROOT,
        KEYWORD_EXTRACTION_DIR,
        EMBEDDINGS_OUTPUT_DIR,
    )

    # 使用与 server_wb 一致的 API（可从环境变量或 key 文件读取）
    base_url = os.getenv("LLM_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3/bots")
    api_key = os.getenv("LLM_API_KEY")
    if not api_key and os.path.isfile(os.path.join(_ROOT, "static", "key1.txt")):
        with open(os.path.join(_ROOT, "static", "key1.txt"), "r", encoding="utf-8") as f:
            api_key = f.read().strip()
    if not api_key:
        print("请设置 LLM_API_KEY 或在 static/key1.txt 中配置 API Key")
        return

    client = OpenAI(base_url=base_url, api_key=api_key)
    model = os.getenv("LLM_MODEL", "bot-20250618131857-l9ffp")

    print("步骤 1/2: 关键词提取（LLM 四分类）...")
    run_keyword_extraction(
        client=client,
        model=model,
        analog_root=ANALOG_TEST1_ROOT,
        output_dir=KEYWORD_EXTRACTION_DIR,
        skip_existing=True,
    )
    print("步骤 2/2: 向量化并保存...")
    run_embed(
        extraction_dir=KEYWORD_EXTRACTION_DIR,
        output_dir=EMBEDDINGS_OUTPUT_DIR,
        analog_root=ANALOG_TEST1_ROOT,
    )
    print("Analog RAG 索引构建完成。")
    print(f"  - 关键词提取结果: {KEYWORD_EXTRACTION_DIR}")
    print(f"  - 向量与元数据: {EMBEDDINGS_OUTPUT_DIR}")


if __name__ == "__main__":
    main()
