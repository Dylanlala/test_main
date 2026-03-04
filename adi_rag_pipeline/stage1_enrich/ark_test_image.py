import os
from volcenginesdkarkruntime import Ark

# 从环境变量中获取您的API KEY，配置方法见：https://www.volcengine.com/docs/82379/1399008
api_key = "3e9cc4e7-1a3b-419f-b22c-2b0b77004498"

client = Ark(
    base_url='https://ark.cn-beijing.volces.com/api/v3',
    api_key=api_key,
)

response = client.responses.create(
    model="doubao-seed-2-0-lite-260215",
    input=[
        {
            "role": "user",
            "content": [

                {
                    "type": "input_image",
                    "image_url": "https://www.analog.com/packages/isc/v2824/zh/isc-0477.png"
                },
                {
                    "type": "input_text",
                    "text": "请你详细描述图中的内容，图中有什么器件，以及器件的位置和前后连接关系描述出来，是用单线还是双向线"

                },
            ],
        }
    ]
)

print(response)