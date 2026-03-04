import json
from sentence_transformers import SentenceTransformer
from scipy.spatial.distance import cosine
import numpy as np
from langchain.prompts import ChatPromptTemplate
from openai import OpenAI
import re
from json_repair import repair_json
import os


os.environ["TOKENIZERS_PARALLELISM"] = "false"


template_search = '''
   # 角色：电子元器件领域专家

    # 任务目标
    从方案数据库中检索与用户设计需求最匹配的方案，输出该方案的ID和完整描述。
    
    # 输入参数
    1. **设计需求**： ##{intention}###
    2. **方案数据库**： ##{database}###
       数据结构：Python字典  
       - Key：方案ID（int格式）  
       - Value：方案描述（文本）  
    
    # 处理要求
    1. 进行语义匹配：比较设计需求与方案数据库中的描述文本的相似度  
    2. 检索规则：选择相似度最高的方案  
    3. 结果输出： 方案ID 完全复制数据库中的原始ID,方案描述完全复制数据库中的原始描述
       ```json
       {{
         "id": 方案ID, 
         "description": 方案描述
       }}
    '''
prompt_template_search = ChatPromptTemplate.from_template(template_search)
def search(design_descriptions,model,maxtokens = 30000,thr = 0.8):
    path = '/data/taoqi/ti_data'
    dir0 = os.listdir(path)
    database = {}
    for i in range(len(dir0)):
        dir1 = os.listdir(path+'/'+dir0[i])
        for j in range(len(dir1)):
            dir2 = path+'/'+dir0[i]+'/'+dir1[j]
            files = os.listdir(dir2)
            for file in files:
                if 'description.json' in file:
                    with open( path+'/'+dir0[i]+'/'+dir1[j]+'/'+file, 'r') as f:
                        data = json.load(f)  # 返回字典或列表[1,8](@ref)
                    database[path+'/'+dir0[i]+'/'+dir1[j]+'/'+file] = data['description']
    # design_descriptions = '11111'+list(database.values())[0]
    # design_descriptions ='该示例系统展示了一种安全云连接物联网网关的构建方法，用于支持对多个无线节点的访问与控制。此设计基于 TM4C12x、TM4C123x、TRF7970A 和 RF430CL330H 等器件，并采用了包含 SimpleLink™ Wi-Fi® CC3100、Bluetooth® 低能耗 CC2650 以及 Sub-1 GHz CC1310 无线微控制器 (MCU) 在内的开发硬件和软件套件。这些资源旨在简化开发流程并加速产品推向市场的速度。'
    user_query_path = list(database.keys())
    user_query = list(database.values())
    design_embeddings = model.encode(design_descriptions)
    query_embedding = model.encode(user_query)
    similarities = [1 - cosine(design_embeddings, emb) for emb in query_embedding]
    similaritiessort = np.argsort(similarities)[::-1]
    ds_query = {}
    ds_databaseid = []
    ds_paths = []
    tokens,id = 0,0
    while tokens<maxtokens and id<len(similaritiessort) and similarities[similaritiessort[id]]>thr:
        ds_query[id] = user_query[similaritiessort[id]]
        ds_databaseid.append(similaritiessort[id])
        ds_paths.append(user_query_path[similaritiessort[id]])
        tokens += len(ds_query[id])
        id+=1
    print(similaritiessort[0],222222,similarities[similaritiessort[0]])
    print(list(database.values())[0])
    return ds_query,ds_databaseid,ds_paths
model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2',cache_folder='/data/alg/fae/paraphrase-multilingual-MiniLM-L12-v2')
base_url = "https://api.deepseek.com"
base_model="deepseek-chat"
with open('./static/key.txt', 'r', encoding='utf-8') as f:
    llmkey = f.read()
client = OpenAI(
    base_url=base_url,
    api_key=llmkey
)
json_pattern = r'```json(.*?)```'

generated_data = { "框图": '',"bom": '',"方案描述":'','网表': '',"cadence": "正在开发中"}
design_descriptions ='该示例系统展示了一种安全云连接物联网网关的构建方法，用于支持对多个无线节点的访问与控制。此设计基于 TM4C12x、TM4C123x、TRF7970A 和 RF430CL330H 等器件，并采用了包含 SimpleLink™ Wi-Fi® CC3100、Bluetooth® 低能耗 CC2650 以及 Sub-1 GHz CC1310 无线微控制器 (MCU) 在内的开发硬件和软件套件。这些资源旨在简化开发流程并加速产品推向市场的速度。'
ds_query,ds_databaseid,ds_paths = search(design_descriptions,model,maxtokens = 30000)
if len(ds_databaseid):
    message_search = prompt_template_search.format_messages(intention=design_descriptions,database=ds_query)
    response_search = client.chat.completions.create(
        model=base_model,
        messages=[
            {"role": "user", "content": message_search[0].content},
        ],
        stream=False
    )
    matches_system = re.findall(json_pattern, response_search.choices[0].message.content, re.DOTALL)
    json_str = matches_system[0].strip()
    json_str = str(repair_json(json_str=json_str, return_objects=False))
    result_json = json.loads(json_str)
    generated_data["方案描述"]=result_json['方案描述']
    # return jsonify(generated_data)  