#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
使用豆包 Ark 多模态模型将图片转为文字（图理解 / 图转文）。
支持本地图片路径与图片 URL；API 与项目内 static/key1.txt、Ark Chat 一致。

使用前请在火山方舟控制台创建并部署「支持视觉的模型」（如豆包·视觉理解等），
将得到的 endpoint 作为 --model 或环境变量 ARK_VISION_MODEL。
"""
import argparse
import base64
import os
import sys
from typing import Optional

# 项目根目录，与 adi_rag_pipeline 一致
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
ARK_BASE_URL = os.getenv("LLM_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3/bots")
ARK_API_KEY_PATH = os.path.join(PROJECT_ROOT, "static", "key1.txt")

# 视觉模型：在方舟控制台创建「支持图片理解」的模型后，把 endpoint 填在这里（如 ep-20241118145939-2lqmt）
DEFAULT_VISION_MODEL = "Doubao-Seed-2.0-Pro"

# 默认提示词：图转文时的提问，可按需修改
DEFAULT_IMAGE_PROMPT = "请详细描述这张图片的内容，包括图中的文字、图表、符号和结构。用中文输出。"


def get_api_key() -> str:
    if os.path.exists(ARK_API_KEY_PATH):
        with open(ARK_API_KEY_PATH, "r", encoding="utf-8") as f:
            return f.read().strip()
    return os.getenv("LLM_API_KEY", "") or os.getenv("ARK_API_KEY", "")


def image_to_data_url(path_or_url: str) -> Optional[str]:
    """
    本地文件转为 data URL（base64）；已是 http(s) 则返回 None（调用方直接用 URL）。
    """
    s = (path_or_url or "").strip()
    if s.startswith("http://") or s.startswith("https://"):
        return None
    if not os.path.isfile(s):
        return None
    try:
        with open(s, "rb") as f:
            raw = f.read()
    except Exception:
        return None
    ext = os.path.splitext(s)[1].lower()
    mime = "image/png" if ext == ".png" else "image/jpeg" if ext in (".jpg", ".jpeg") else "image/png"
    b64 = base64.standard_b64encode(raw).decode("ascii")
    return f"data:{mime};base64,{b64}"


def image_to_text(
    image_path_or_url: str,
    prompt: Optional[str] = None,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
) -> str:
    """
    调用豆包 Ark 视觉模型，将一张图片转为文字描述。

    :param image_path_or_url: 本地图片路径或图片 URL
    :param prompt: 用户提示，默认让模型描述图片内容（中文）
    :param model: 视觉模型 endpoint ID，不传则用环境变量 ARK_VISION_MODEL
    :param api_key: API Key，不传则从 static/key1.txt 或环境变量读取
    :param base_url: API 根地址，不传则用 LLM_BASE_URL / 默认 Ark
    :return: 模型返回的文本
    """
    from openai import OpenAI

    model = (model or os.getenv("ARK_VISION_MODEL", "") or DEFAULT_VISION_MODEL or "").strip()
    if not model:
        raise ValueError(
            "未指定视觉模型。请在本文件顶部修改 DEFAULT_VISION_MODEL，"
            "或设置环境变量 ARK_VISION_MODEL / 传入 --model"
        )

    key = (api_key or get_api_key()).strip()
    if not key:
        raise ValueError("未配置 API Key，请设置 static/key1.txt 或环境变量 LLM_API_KEY / ARK_API_KEY")

    url = (base_url or ARK_BASE_URL).strip()
    client = OpenAI(base_url=url, api_key=key)

    user_prompt = (prompt or DEFAULT_IMAGE_PROMPT).strip()

    # 构建多模态 content：先文字，再图片
    data_url = image_to_data_url(image_path_or_url)
    if data_url:
        content = [
            {"type": "text", "text": user_prompt},
            {"type": "image_url", "image_url": {"url": data_url}},
        ]
    else:
        # 已是 http(s) URL
        content = [
            {"type": "text", "text": user_prompt},
            {"type": "image_url", "image_url": {"url": image_path_or_url.strip()}},
        ]

    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": content}],
        max_tokens=2048,
        stream=False,
    )
    return (resp.choices[0].message.content or "").strip()


def main():
    parser = argparse.ArgumentParser(
        description="使用豆包 Ark 将图片转为文字（需在方舟控制台配置支持视觉的模型）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python ark_image_to_text.py --image signal_chain_0519.png
  python ark_image_to_text.py --image https://example.com/diagram.png --prompt "图中有哪些芯片型号？"
  set ARK_VISION_MODEL=ep-xxxx & python ark_image_to_text.py --image ./pic.png
        """,
    )
    parser.add_argument("--image", "-i", required=True, help="本地图片路径或图片 URL")
    parser.add_argument("--prompt", "-p", default=None, help="对图片的提问或描述指令，默认：描述图片内容（中文）")
    parser.add_argument("--model", "-m", default=None, help="Ark 视觉模型 endpoint ID（也可用环境变量 ARK_VISION_MODEL）")
    parser.add_argument("--out", "-o", default=None, help="将输出写入该文件，不指定则打印到 stdout")
    args = parser.parse_args()

    try:
        text = image_to_text(
            image_path_or_url=args.image,
            prompt=args.prompt,
            model=args.model,
        )
    except ValueError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"调用失败: {e}", file=sys.stderr)
        sys.exit(1)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"已写入: {args.out}")
    else:
        print(text)


if __name__ == "__main__":
    main()
