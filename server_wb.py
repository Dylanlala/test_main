from flask import Flask, request, send_from_directory, jsonify, send_file, session
from flask_cors import CORS
import subprocess
from openai import OpenAI
from faeutils import *
from generatedata import noBaseGenerator
from sentence_transformers import SentenceTransformer
from datetime import datetime, timezone, timedelta
from io import BytesIO
import tempfile
import os
import threading
import uuid
from replace import get_alternate_materials
from whitepdf import WhitepaperGenerator
from rag_expert_search import create_rag_retriever
import json
import shutil
from PIL import ImageFont
# from langchain.embeddings.base import Embeddings
# from typing import List
# from langchain.embeddings import HuggingFaceEmbeddings
from langchain_community.embeddings import HuggingFaceEmbeddings


os.environ["TOKENIZERS_PARALLELISM"] = "false"
json_pattern = r'```json(.*?)```'  # r'\{(?:[^{}]|(?:\{.*?\}))*\}'


#
# class SentenceTransformerEmbeddings(Embeddings):
#     def __init__(self, model):
#         self.model = model
#
#     def embed_documents(self, texts: List[str]) -> List[List[float]]:
#         """为文档列表生成嵌入"""
#         embeddings = self.model.encode(texts, convert_to_tensor=False)
#         return embeddings.tolist()
#
#     def embed_query(self, text: str) -> List[float]:
#         """为查询生成嵌入"""
#         embedding = self.model.encode(text, convert_to_tensor=False)
#         return embedding.tolist()

# embeddingmodel = SentenceTransformer('../paraphrase-multilingual-MiniLM-L12-v2', local_files_only=True,
#                                      cache_folder='/data/alg/fae/paraphrase-multilingual-MiniLM-L12-v2')
# sentence_model = SentenceTransformer('../paraphrase-multilingual-MiniLM-L12-v2', local_files_only=True,
#                                      cache_folder='/data/alg/fae/paraphrase-multilingual-MiniLM-L12-v2')
# embeddingmodel = SentenceTransformerEmbeddings(sentence_model)


# 替换原来的 SentenceTransformer 初始化
embeddingmodel = HuggingFaceEmbeddings(
    model_name='../paraphrase-multilingual-MiniLM-L12-v2',
    cache_folder='/data/alg/fae/paraphrase-multilingual-MiniLM-L12-v2',
    model_kwargs={'local_files_only': True}
)
base_url = "https://ark.cn-beijing.volces.com/api/v3/bots"
# 定义两种模式的模型
MODELS = {
    'fast': "bot-20250618131857-l9ffp",  # 快速模式
    'precise': "bot-20250827135630-2rprd"  # 精准模式
}
# 东八区
SHA_TZ = timezone(timedelta(hours=8))
with open('./static/key1.txt', 'r', encoding='utf-8') as f:
    llmkey = f.read()

# llmkey = 'sk-JtTvlpK59YIGu4T0FY1I56U5r2MfdQXVznrXV1ZKzzdodtMj'
# MODELS['precise'] = 'gpt-5.2'
# base_url = "https://api.lingyaai.cn/v1"

# 创建基础客户端（稍后根据模式选择模型）
base_client = OpenAI(
    base_url=base_url,
    api_key=llmkey
)

app = Flask(__name__, static_folder='static')
CORS(app, resources={r"/*": {"origins": "*"}})  # 增强CORS配置
app.secret_key = 'TebtCq3ERvb5M4nDErM'

app.logger.disabled = True  # 禁用Flask的日志处理器

# --- 然后重新配置你的日志 ---
import logging

logging.basicConfig(
    level=logging.WARNING,
    format='%(asctime)s %(levelname)s %(name)s: %(message)s',
    force=True
)

# 确保设置fontTools及其子模块的日志级别
for _n in ('fontTools', 'fontTools.subset', 'fontTools.ttLib', 'PIL', 'weasyprint'):
    logging.getLogger(_n).setLevel(logging.WARNING)

RESULT_DIR = "./result"
STATIC_DIR = "./static"
maxblock = 2
font_path = './SimHei.ttf'
font_size = 100
dsmaxtokens = 3000
embeddingthr = 0.8
cut_chip = True
font = ImageFont.truetype(font_path, font_size)
PDF_DIR = "./static/pdfs"

LOG_FILE = os.path.join(RESULT_DIR, 'generation.log')
lock = threading.Lock()
# 存储生成器实例的全局字典
generator_instances = {}
os.makedirs(RESULT_DIR, exist_ok=True)
os.makedirs(STATIC_DIR, exist_ok=True)
os.makedirs(PDF_DIR, exist_ok=True)

# RAG检索器配置（可选）
# 优先使用环境变量，否则使用默认路径
RAG_DATA_PATH = os.getenv('RAG_DATA_PATH', './all_data_20.json')  # 默认使用 all_data_20.json
RAG_INDEX_PATH = os.getenv('RAG_INDEX_PATH', './expert_case_index')  # 索引保存路径
# Analog RAG：基于 analog_test1 的方案检索（与 lina_code_new 一致的四类关键词+FAISS）
ANALOG_RAG_ENABLE = os.getenv('ANALOG_RAG_ENABLE', '0').strip().lower() in ('1', 'true', 'yes')
ANALOG_RAG_EMBEDDINGS_DIR = os.getenv('ANALOG_RAG_EMBEDDINGS_DIR', '')  # 为空时使用 analog_rag 默认路径
rag_retriever = None

# 优先初始化 Analog RAG（analog_test1 方案库，与 lina 做法一致）
if ANALOG_RAG_ENABLE:
    try:
        from analog_rag import create_analog_rag_retriever
        _analog_dir = ANALOG_RAG_EMBEDDINGS_DIR or None
        rag_retriever = create_analog_rag_retriever(
            embeddings_dir=_analog_dir,
            client=base_client,
            model=MODELS.get('fast', 'bot-20250618131857-l9ffp'),
        )
        if rag_retriever:
            print("Analog RAG 检索器初始化成功（analog_test1 方案库）")
        else:
            rag_retriever = None
    except Exception as e:
        print(f"Analog RAG 检索器初始化失败: {e}，将尝试使用原有 RAG")
        rag_retriever = None

# 若未启用或未成功使用 Analog RAG，则使用原有 expert RAG（all_data_20.json）
if rag_retriever is None and RAG_DATA_PATH and os.path.exists(RAG_DATA_PATH):
    try:
        print(f"正在初始化RAG检索器，数据路径: {RAG_DATA_PATH}")
        rag_retriever = create_rag_retriever(
            embedding_model=embeddingmodel,
            data_path=RAG_DATA_PATH,
            index_path=RAG_INDEX_PATH,
            rebuild_index=False  # 如果索引已存在，直接加载
        )
        print("RAG检索器初始化成功！")
    except Exception as e:
        print(f"RAG检索器初始化失败: {e}，将不使用历史方案检索功能")
        rag_retriever = None
elif rag_retriever is None:
    print("未配置RAG数据路径且未启用 Analog RAG，将不使用历史方案检索功能")
    print("提示：设置环境变量 RAG_DATA_PATH 或 ANALOG_RAG_ENABLE=1 来启用RAG检索功能")


@app.route('/')
def serve_index():
    """主页面路由"""
    return send_from_directory(STATIC_DIR, 'index.html')


def log_generation(save_dir: str, intention: str):
    """线程安全地把一次生成记录到文件"""
    with lock:
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            # 一行 JSON，方便后续脚本解析
            record = {
                'timestamp': datetime.now(SHA_TZ).isoformat(timespec='seconds'),
                'save_dir': save_dir,
                'intention': intention
            }
            f.write(json.dumps(record, ensure_ascii=False) + '\n')


def get_save_dir():
    """所有路由统一拿目录"""
    d = session.get('save_dir')
    if not d or not os.path.isdir(d):
        raise ValueError('目录已失效，请重新生成设计')
    return d


@app.route('/<path:filename>')
def serve_static(filename):
    """静态文件路由"""
    return send_from_directory(STATIC_DIR, filename)


@app.route('/generate_all', methods=['POST'])
def generate_all():
    """生成所有电路数据"""
    data = request.json
    intention = data.get('prompt', '')
    mode = data.get('mode', 'fast')  # 默认为快速模式
    is_first = data.get('is_first', True)  # 新增标志位，默认为True

    # 获取或创建会话ID
    session_id = session.get('session_id')
    if not session_id:
        session_id = str(uuid.uuid4())
        session['session_id'] = session_id

    # 检查是否已有生成器实例
    if is_first or session_id not in generator_instances:
        # 创建临时文件夹
        save_dir = tempfile.mkdtemp(prefix="tmp_", dir=RESULT_DIR)
        print(f'--------临时文件已创建： {save_dir}-------------')
        clean_old_files(RESULT_DIR=save_dir)
        session['save_dir'] = save_dir

        # 根据模式选择模型
        base_model = MODELS.get(mode, MODELS['fast'])

        # 创建新的生成器实例并保存到全局字典
        generator = noBaseGenerator(
            embeddingmodel,
            base_client,
            base_model,
            json_pattern,
            maxblock,
            cut_chip,
            save_dir,
            rag_retriever=rag_retriever  # 传入RAG检索器（如果已初始化）
        )
        generator_instances[session_id] = generator
        print(f'-------------{mode} mode generate (new generator)-------------')
    else:
        # 复用已有的生成器实例
        generator = generator_instances[session_id]
        save_dir = session['save_dir']
        print(f'-------------{mode} mode generate (reuse generator)-------------')

    print(f'Using model: {generator.base_model}')
    print(f'Is first generation: {is_first}')

    # ★ 记录到文件
    log_generation(save_dir, intention)

    # 根据是否是首次生成选择不同的函数
    if is_first:
        generated_data = generator.noBaseGenerate(intention)
    else:
        # 获取对话历史
        conversation_history = data.get('conversation_history', [])
        generated_data = generator.multiGenerate(intention, conversation_history)

    with lock:
        with open("./result/history.txt", 'a', encoding='utf-8') as f:
            # 一行 JSON，方便后续脚本解析
            history = [{'role': 'user', 'content': intention}, {'role': 'assistant', 'content': generator.generatedata}]
            f.write(json.dumps(history, ensure_ascii=False) + '\n')
    return jsonify(generated_data)


@app.route('/get_alternate_materials', methods=['POST'])
def get_alternate_materials_route():
    """获取替代料信息"""
    try:
        save_dir = get_save_dir()
        data = request.json
        model = data.get('model', '')
        description = data.get('description', '')
        design_intention = data.get('design_intention', '')
        mode = data.get('mode', 'fast')  # 获取模式参数

        print(model, description, design_intention, f"Mode: {mode}")
        if not model:
            return jsonify({"error": "未提供型号参数"}), 400

        # 根据模式选择模型
        base_model = MODELS.get(mode, MODELS['fast'])

        # 创建对应模式的客户端
        mode_client = OpenAI(
            base_url=base_url,
            api_key=llmkey
        )

        # 调用物料替代函数
        alternate_data = get_alternate_materials(
            title=model,
            description=description,
            design_intention=design_intention,
            output=save_dir,
            ds_chat=mode_client,
            replace=True,
            auto_replace=False
        )

        return jsonify(alternate_data)

    except Exception as e:
        print(f"获取替代料失败: {str(e)}")
        return jsonify({"error": f"获取替代料失败: {str(e)}"}), 500


@app.route('/generate_preview', methods=['POST'])
def generate_preview():
    """将Draw.io XML转换为图片"""
    xml_content = request.data.decode('utf-8')

    try:
        # 创建临时XML文件
        with tempfile.NamedTemporaryFile(suffix='.xml', delete=False) as tmp_xml:
            tmp_xml.write(xml_content.encode('utf-8'))
            tmp_xml_path = tmp_xml.name

        # 创建临时PNG文件 - 使用固定路径保存以便调试
        tmp_png_path = os.path.join(tempfile.gettempdir(), 'drawio_preview.png')

        # 设置环境变量 - 解决libGL错误
        env = os.environ.copy()
        env['LIBGL_ALWAYS_SOFTWARE'] = '1'
        env['GALLIUM_DRIVER'] = 'llvmpipe'

        # 使用draw.io命令行工具转换XML为PNG
        # 在无头服务器上使用xvfb-run
        result = subprocess.run([
            'xvfb-run', '-a', 'drawio',
            '-x',  # 导出
            '-f', 'png',  # 导出格式为PNG
            '-o', tmp_png_path,  # 输出文件
            tmp_xml_path  # 输入文件
        ],
            env=env,  # 添加环境变量
            capture_output=True,
            text=True,
            timeout=30)

        # 读取PNG文件并返回
        with open(tmp_png_path, "rb") as f:
            png_data = f.read()

        # 保存图片副本用于调试
        debug_png_path = os.path.join(tempfile.gettempdir(), 'debug_preview.png')
        with open(debug_png_path, 'wb') as f:
            f.write(png_data)
        print(f"调试图片已保存到: {debug_png_path}")

        # 清理临时文件
        os.unlink(tmp_xml_path)
        os.unlink(tmp_png_path)

        # 创建内存中的文件对象
        img_io = BytesIO(png_data)
        img_io.seek(0)

        return send_file(img_io, mimetype='image/png')

    except subprocess.TimeoutExpired:
        print("XML转PNG操作超时")
        return jsonify({"error": "转换操作超时"}), 500
    except Exception as e:
        print(f"生成预览图失败: {str(e)}")
        # 保存错误信息
        error_log_path = os.path.join(tempfile.gettempdir(), 'drawio_exception.log')
        with open(error_log_path, 'w') as f:
            f.write(f"Exception: {str(e)}\n")

        return jsonify({
            "error": f"无法生成预览图: {str(e)}",
            "log_path": error_log_path
        }), 500


@app.route('/generate_pdf', methods=['POST'])
def generate_pdf():
    """生成设计白皮书PDF"""
    try:
        data = request.json
        save_dir = get_save_dir()
        # 提取数据
        intention = data.get('intention', '')
        system_block = data.get('system_block', '')
        bom = data.get('bom', [])
        description = data.get('description', '')
        selection_notes = {}
        circuit_paths = data.get('circuit_paths', [])
        generator = WhitepaperGenerator(
            openai_api_key="your_openai_api_key",
            unsplash_api_key="o4kgIGFSfAkLN_E8vn8I1fE6TebtCq3ERvb5M4nDErM",  # 替换为你的实际密钥
            output=save_dir
        )
        whitepaper_path = generator.generate_whitepaper(
            intention, system_block, bom, description, selection_notes, circuit_paths
        )

        return send_file(
            whitepaper_path,
            as_attachment=False,  # 设置为False以便在浏览器中查看
            download_name='设计方案书.pdf',
            mimetype='application/pdf'
        )

    except Exception as e:
        print(f"生成PDF失败: {str(e)}")
        return jsonify({
            "success": False,
            "error": f"生成PDF失败: {str(e)}"
        }), 500


if __name__ == '__main__':
    # 检查依赖工具
    required_tools = ['netlistsvg', 'rsvg-convert']
    for tool in required_tools:
        if not shutil.which(tool):
            raise EnvironmentError(f"Required tool not found: {tool}")

    # 启动服务器
    app.run(host='0.0.0.0', port=8000, debug=True, threaded=True)  # 8188  