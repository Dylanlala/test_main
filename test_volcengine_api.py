#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
火山引擎 Ark API 连通性测试。
使用前：pip install openai
建议将密钥放到环境变量，不要提交到仓库。
"""
import os

# 可从环境变量覆盖，便于本地测试
VOLCENGINE_API_KEY = os.getenv("VOLCENGINE_API_KEY", "88632c3b-7c51-4517-83a1-c77957720f11")
VOLCENGINE_BASE_URL = os.getenv("VOLCENGINE_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
VOLCENGINE_MODEL = os.getenv("VOLCENGINE_MODEL", "bot-20251202172548-dp7bp")


def main():
    from openai import OpenAI

    client = OpenAI(base_url=VOLCENGINE_BASE_URL, api_key=VOLCENGINE_API_KEY)
    print(f"Base URL: {VOLCENGINE_BASE_URL}")
    print(f"Model:    {VOLCENGINE_MODEL}")
    print("调用中...")

    try:
        resp = client.chat.completions.create(
            model=VOLCENGINE_MODEL,
            messages=[{"role": "user", "content": "请用一句话说「你好」并说明当前日期。"}],
            max_tokens=256,
            stream=False,
        )
        text = (resp.choices[0].message.content or "").strip()
        print("--- 成功 ---")
        print("回复:", text)
        return 0
    except Exception as e:
        print("--- 失败 ---")
        print(type(e).__name__, str(e))
        return 1


if __name__ == "__main__":
    exit(main())
