import copy
import pandas as pd
import copy
from faeutils import *
import time
from mermaid_visualizer_graphviz import mermaid_to_graphviz
from mermaid_visualizer_nine_grid import generate_nine_grid
import base64
import uuid
from elasticsearch import Elasticsearch
import re
import json
from json_repair import repair_json
from concurrent.futures import ThreadPoolExecutor, as_completed
from replace_batch import get_alternate_materials_batch
from prompt import template_update, template_system,template_mapping,template_analysis,template_multi,template_correction
from langchain.prompts import ChatPromptTemplate
from pathlib import Path
import PyPDF2
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
import os
from langchain_community.document_loaders import PyPDFLoader
from langchain.schema import Document
import requests

MAX_CANDIDATES = 500
max_len = 50000

# base_model_precise = "bot-20250827135630-2rprd"

# 品牌列表常量
PREFERRED_BRANDS = ['AMLOGIC|晶晨', 'BELLING|贝岭', 'HDSC|华大半导体', 'HISILICON|海思', 'MAXIC|美芯晟', 'MICRONE|微盟电子', 'MOLEX|莫仕', 'NVIDIA|英伟达', 'Qorvo|超群', 'SGMICRO|圣邦', 'Silergy|矽力杰', 'Centec|盛科', 'Lontium|龙迅', 'Neoway|有方', 'FM|复旦微', 'AMD|超威', 'ams OSRAM|艾迈斯 欧司朗', 'ADI|亚德诺', 'CSMT|成都华微', 'Epson|爱普生', 'FTDI|飞特帝亚', 'GD|兆易创新', 'ISSI|芯成', 'Lattice|莱迪思', 'MAXLINEAR|迈凌', 'Microchip|微芯', 'Micron|美光', 'Murata|村田', 'Nexperia|安世',
     'Nuvoton|新唐', 'NXP|恩智浦', 'O2Micro|凹凸科技', 'Omnivision|豪威科技', 'onsemi|安森美', 'OTAX|欧达可',
     'Renesas|瑞萨', 'Richwave|立积', 'Rochester|罗彻斯特', 'SEMTECH|升特', 'WeEn|瑞能', 'UniIC|紫光国芯',
     'Phytium|飞腾', 'WILLSEMI|韦尔半导体', 'qualcomm|高通', '3PEAK|思瑞浦', 'Allystar|华大北斗',
     'CXMT|长鑫存储', 'GOKE|国科微', 'Longsys|江波龙', 'MONTAGE|澜起科技', 'MONTAGE LZ|澜至', 'NCEPOWER|新洁能',
     'Quectel|移远', 'XMC|武汉新芯', 'UNIC|紫光', 'UNISOC|紫光展锐', 'GOOWI|高为', 'LITEON|光宝',
     'Solomon|晶门', 'Ittim|思存', 'MXCHIP|庆科', 'Nova|纳瓦', 'Barrot|百瑞', 'Aurasemi|奥拉',
     'Supermicro|超微', 'WUQi|物奇', 'Smartlink|捷联', 'Kangxi|康希通信', 'Netswift|网迅', 'POWEV|嘉合劲威',
     '2Pai Semi|荣湃', 'MotorComm|裕太微电子', 'YMTC|长江存储', 'Fullhan|富瀚微', 'Tigo|金泰克',
     'BIWIN|佰维存储', 'CR micro|华润微', 'Chipanalog|川土微', 'SENASIC|琻捷', 'Nanochap|暖芯迦', 'VANGO|万高',
     'SIMCom|芯讯通', 'Hosonic|鸿星', 'FN-LINK|欧智通', 'AWINIC|艾为', 'Hollyland|好利来', 'zhaoxin|兆芯',
     'HORIZON|地平线', 'GALAXYCORE|格科微', 'CEC Huada Electronic|华大电子', 'IVCT|瞻芯', 'HLX|中电熊猫',
     'C*Core|苏州国芯', 'SENSYLINK|申矽凌', 'ZhiXin|智芯', 'Hiksemi|海康存储', 'SiEngine|芯擎',
     'FREQCHIP|富芮坤', 'Unicore|和芯星通', 'Sunshine|烨映', 'Thundercomm|创通联达', 'Netforward|楠菲',
     'NewCoSemi|新港海岸', 'Watech|华太', 'legendsemi|领慧立芯', 'LUHUI|麓慧', 'Denglin|登临', 'Aich|爱旗',
     'DapuStor|大普微', 'XHSC|小华半导体', 'GONGMO|共模半导体', 'Axera|爱芯元智', 'Dropbeats|奇鲸',
     'Giantohm Micro|鼎声微', 'Simchip|芯炽', 'silicon|芯迈', 'Senarytech|深蕾', 'KUNLUNXIN|昆仑芯',
     'Wedosemi|苇创微', 'analogysemi|类比半导体', 'JEMO|景美', 'AICXTEK|归芯科技', 'KylinSoft|麒麟软件',
     'GZLX|广州领芯', 'POWER-SNK|华为数字能源', 'Dongqin|东勤', 'Iluvatar|天数智芯', 'VELINKTECH|首传微',
     'chipl_tech|中昊芯英', 'Paddle Power|派德芯能', 'JinTech|晋达', 'Wodposit|沃存']


SECONDARY_MODULES_MAP = {
    "电源": ['AC-DC控制器', 'DC-DC稳压器', 'DC/DC控制器', 'LDO稳压器', 'PMIC', '电源模块', '负载开关', '参考基准', '监控复位', '保险丝', '无线充电', '以太网供电', '电池管理', 'OCP/OVP', '充电管理IC', '充电模块'],
    "信号采集": ['放大器AMPLIFIER', '比较器', '数据转换ADC/DAC', '逻辑器件', '接口隔离', '信号开关', '音频管理', '视频管理', '模拟前端AFE', '信号调理器', '特殊信号链', '传感器',  '信号接口（电平转换、GPIO拓展）', 'IMU', 'MEMS', '编码器', 'HDMI', '多路复用器', '数字电位器', '表计/计量芯片'],
    "存储": ['DDR', 'FLASH', 'EEPROM', 'EMCP', 'EMMC', 'UFS', 'HDD', 'SSD', '内存条', '存储卡', '存储控制器'],
    "通信和接口": ['WIFI', '蓝牙', 'ZIGBEE', 'NFC', 'RFID', 'UWB', '星闪', 'SUB-1G', '2.4GHZ', 'LORA', 'NB-IOT', 'GNSS定位', '手机通信芯片', '蜂窝通信模组(4G/5G/NB/CAT1)', 'RS232', 'RS485', 'I2C', 'UART', 'USB', 'CAN', 'LINK', 'PCIE', 'SATA', 'ETHERCAT/PHY', '隔离芯片', 'SERDES', 'A2B', 'SBC', 'LVDS', 'IR红外', 'JTAG', 'SPI', 'SDIO'],
    "主控": ['CPU', 'GPU', 'MCU', 'MPU', 'SOC', 'FPGA', 'CPLD', 'DSP'],
    "时钟": ['晶振', 'RTC', '时钟缓冲器', '去抖时钟', '高精度网络时钟器'],
    "人机界面": ['触摸TOUCH/触觉反馈', 'MIPI/LVDS/EDP/HDMI/RGB/SPI屏', '键盘', '鼠标', '按键/开关', 'SPEAK', 'MIC', '摄像头', '显示驱动'],
    "控制驱动": ['二极管', '三极管', '晶闸管', 'MOSFET', 'IGBT', 'SPS', 'SIC', 'GAN', 'IPM模块', '栅极驱动器', '电机驱动', 'I/O BUFFER', 'FET DRIVER', '三八译码器', '光电器件'],
    "其他": ['连接器', '阻容感', 'RESISTORS/CAPACITOR/INDUCTORS', '磁珠', 'TVS', '继电器', '电池', '电机', '蜂鸣器', '线缆', '适配器', '断路器', '加密',  '天线', '灯珠', '电阻网络']}
VALID_PRIMARIES = ["电源", "信号采集", "存储", "通信和接口", "主控", "时钟", "人机界面", "控制驱动", "其他"]

prompt_template_update = ChatPromptTemplate.from_template(template_update)
prompt_template_system = ChatPromptTemplate.from_template(template_system)
prompt_template_mapping = ChatPromptTemplate.from_template(template_mapping)
prompt_template_multi = ChatPromptTemplate.from_template(template_multi)
prompt_template_analysis = ChatPromptTemplate.from_template(template_analysis)
prompt_template_correction = ChatPromptTemplate.from_template(template_correction)

class SetEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, set):
            return list(obj)
        return json.JSONEncoder.default(self, obj)


def remove_citations(text):
    pattern = r'\[\d+\]'
    return re.sub(pattern, '', text)



class noBaseGenerator:
    def __init__(self, embeddingmodel, client, base_model, json_pattern, maxblock, cut_chip, output='./result', rag_retriever=None):
        self.client = client
        self.base_model = base_model
        self.client1 = client
        self.base_model1 = base_model
        self.json_pattern = json_pattern
        self.maxblock = maxblock
        self.cut_chip = cut_chip
        self.embeddingmodel = embeddingmodel
        self.output = output
        self.generatedata = {}
        self.partdis = True
        self.intention = ''
        self.history = 0
        self.rag_retriever = rag_retriever  # RAG检索器（可选）




    def update_system_modules_based_on_mapping(self, system_modules, mapping_results, bom_data):
        """根据映射结果更新系统模块和BOM（确保每个ID独立）"""

        # 重新构建系统模块结构
        new_system_modules = {
            "电源": [], "信号采集": [], "存储": [], "通信和接口": [],
            "主控": [], "时钟": [], "人机界面": [], "控制驱动": [], "其他": []
        }

        # 创建ID到新分类的映射
        id_to_new_classification = {}

        # 遍历原始系统模块的每个条目
        for primary_module, secondary_list in system_modules.items():
            for secondary_item in secondary_list:
                if '#' in secondary_item:
                    try:
                        sec_name, module_ids_str = secondary_item.split('#', 1)
                        sec_name = sec_name.strip()
                        module_ids = [id.strip() for id in module_ids_str.split(',')]

                        # 为每个ID单独处理
                        for module_id in module_ids:
                            # 获取映射结果（如果有）
                            new_primary = primary_module
                            new_secondary = sec_name

                            if module_id in mapping_results:
                                mapping_info = mapping_results[module_id]
                                new_primary = mapping_info["primary_module"]
                                new_secondary = mapping_info["secondary_module"]

                            # 构建新的条目字符串（每个ID独立）
                            new_module_entry = f"{new_secondary}#{module_id}"

                            # 添加到新的一级模块
                            if new_primary not in new_system_modules:
                                new_system_modules[new_primary] = []
                            new_system_modules[new_primary].append(new_module_entry)

                            # 保存映射关系用于更新BOM
                            id_to_new_classification[module_id] = new_secondary
                    except ValueError:
                        # 格式错误，保留原样
                        if primary_module not in new_system_modules:
                            new_system_modules[primary_module] = []
                        new_system_modules[primary_module].append(secondary_item)
                else:
                    # 没有#，直接保留
                    if primary_module not in new_system_modules:
                        new_system_modules[primary_module] = []
                    new_system_modules[primary_module].append(secondary_item)

        # 更新BOM：更新零件名称
        updated_bom = []
        for bom_item in bom_data:
            bom_id_str = bom_item.get("元件ID", "")
            individual_bom_ids = [id.strip() for id in bom_id_str.split(',')]

            # 获取所有ID对应的零件名称
            part_names = []
            for bom_id in individual_bom_ids:
                if bom_id in id_to_new_classification:
                    part_names.append(id_to_new_classification[bom_id])
                else:
                    part_names.append(bom_item["零件名称"])

            # 去重并合并
            unique_part_names = list(set(part_names))
            part_name = ", ".join(unique_part_names) if unique_part_names else bom_item["零件名称"]

            # 更新零件名称
            updated_bom_item = bom_item.copy()
            updated_bom_item["零件名称"] = part_name
            updated_bom.append(updated_bom_item)

        return new_system_modules, updated_bom

    def correct_module_classification(self, result_json):
        """
        根据SECONDARY_MODULES_MAP校验和修正二级模块的归属
        将不合理的二级模块移动到预定义的正确一级模块下
        """
        # 创建映射：二级模块名称 -> 正确的一级模块
        secondary_to_primary = {}
        for primary, secondaries in SECONDARY_MODULES_MAP.items():
            for secondary in secondaries:
                # 标准化名称（大写，去除空格）
                normalized_secondary = secondary.upper().replace(" ", "")
                secondary_to_primary[normalized_secondary] = primary

        # 创建新的系统模块结构
        new_system_modules = {
            "电源": [], "信号采集": [], "存储": [], "通信和接口": [],
            "主控": [], "时钟": [], "人机界面": [], "控制驱动": [], "其他": []
        }

        # 存储需要更新的BOM零件名称映射
        id_to_new_name = {}

        # 遍历原始系统模块
        for primary_module, secondary_list in result_json["系统模块"]["模块"].items():
            for secondary_item in secondary_list:
                if '#' in secondary_item:
                    try:
                        sec_name, module_ids_str = secondary_item.split('#', 1)
                        sec_name = sec_name.strip()
                        module_ids = [id.strip() for id in module_ids_str.split(',')]

                        # 标准化二级模块名称
                        normalized_sec = sec_name.upper().replace(" ", "")

                        # 检查是否在预定义映射中
                        if normalized_sec in secondary_to_primary:
                            correct_primary = secondary_to_primary[normalized_sec]

                            # 如果当前一级模块不正确，则移动到正确的一级模块
                            if primary_module != correct_primary:
                                print(f"修正: 将'{sec_name}'从'{primary_module}'移动到'{correct_primary}'")

                                # 更新ID到新名称的映射
                                for module_id in module_ids:
                                    id_to_new_name[module_id] = sec_name

                                # 添加到正确的一级模块
                                new_entry = f"{sec_name}#{','.join(module_ids)}"
                                if correct_primary not in new_system_modules:
                                    new_system_modules[correct_primary] = []
                                new_system_modules[correct_primary].append(new_entry)
                                continue

                        # 如果不需要移动，保留原样
                        if primary_module not in new_system_modules:
                            new_system_modules[primary_module] = []
                        new_system_modules[primary_module].append(secondary_item)
                    except ValueError:
                        # 格式错误，保留原样
                        if primary_module not in new_system_modules:
                            new_system_modules[primary_module] = []
                        new_system_modules[primary_module].append(secondary_item)
                else:
                    # 没有#，直接保留
                    if primary_module not in new_system_modules:
                        new_system_modules[primary_module] = []
                    new_system_modules[primary_module].append(secondary_item)

        # 更新系统模块
        result_json["系统模块"]["模块"] = new_system_modules

        # 更新BOM中的零件名称
        for bom_item in result_json["bom"]:
            bom_id_str = bom_item.get("元件ID", "")
            individual_bom_ids = [id.strip() for id in bom_id_str.split(',')]

            # 获取所有ID对应的新零件名称
            part_names = []
            for bom_id in individual_bom_ids:
                if bom_id in id_to_new_name:
                    part_names.append(id_to_new_name[bom_id])
                else:
                    part_names.append(bom_item["零件名称"])

            # 去重并合并
            unique_part_names = list(set(part_names))
            bom_item["零件名称"] = ", ".join(unique_part_names) if unique_part_names else bom_item["零件名称"]

        return result_json

    def system_gen(self,  intention):
        # RAG检索：获取相似历史方案（如果RAG检索器可用）
        expert_cases_text = ""
        if self.rag_retriever:
            try:
                similar_cases = self.rag_retriever.retrieve_similar_cases(
                    query=intention,
                    top_k=3,
                    similarity_threshold=0.6
                )
                if similar_cases:
                    expert_cases_text = self.rag_retriever.format_cases_for_llm(
                        similar_cases,
                        max_tokens=800
                    )
                    print(f"RAG检索到 {len(similar_cases)} 个相似历史方案")
                    # 保存检索结果用于调试
                    try:
                        with open(f'{self.output}/rag_retrieved_cases.json', 'w', encoding='utf-8') as f:
                            json.dump(similar_cases, f, ensure_ascii=False, indent=2)
                    except:
                        pass
            except Exception as e:
                print(f"RAG检索失败: {e}，继续使用无RAG模式")
                expert_cases_text = ""
        else:
            expert_cases_text = ""
        
        # 如果没有检索到结果，使用空字符串（模板会处理）
        if not expert_cases_text:
            expert_cases_text = "暂无历史参考方案。"
        
        message_analysis = prompt_template_analysis.format_messages(intention=intention, expert_cases=expert_cases_text)
        full_prompt_content = message_analysis[0].content
        try:
            response_analysis = self.client.chat.completions.create(
                model=self.base_model,
                messages=[
                    {"role": "user", "content": full_prompt_content},
                ],
                max_tokens=8000,  # 保持足够的token用于生成长BOM
                stream=False
            )
        except Exception as e:
            print(f"Model generation failed: {e}")
            raise e
        with open(f'{self.output}/message_system_1.txt', 'w', encoding='utf-8') as f:
            f.write(response_analysis.choices[0].message.content)
        
        # 在system生成阶段也注入专家案例（如果可用）
        message_system = prompt_template_system.format_messages(
            intention=intention,
            analysis=response_analysis.choices[0].message.content,
            expert_cases=expert_cases_text
        )

        full_prompt_content = message_system[0].content
        try:
            response_system = self.client.chat.completions.create(
                model=self.base_model,
                messages=[
                    {"role": "user", "content": full_prompt_content},
                ],
                max_tokens=8000,  # 保持足够的token用于生成长BOM
                stream=False
            )
        except Exception as e:
            print(f"Model generation failed: {e}")
            raise e
        savecontent = response_system.choices[0].message.content

        # 调试保存
        try:
            with open(f'{self.output}/message_system_2.txt', 'w', encoding='utf-8') as f:
                f.write(savecontent)
        except Exception:
            pass

        # --- JSON 解析与修复 ---
        try:
            result_json = json.loads(savecontent)
        except json.JSONDecodeError:
            # 1. 尝试正则提取 JSON
            matches_system = re.findall(self.json_pattern, savecontent, re.DOTALL)
            if not matches_system:
                dict_pattern = r'(\{.*\})'
                matches_system = re.findall(dict_pattern, savecontent, re.DOTALL)

            if matches_system:
                json_str = matches_system[0].strip()
                try:
                    # return_objects=True 比 loads(str(repair)) 更安全
                    result_json = repair_json(json_str=json_str, return_objects=True)
                except Exception:
                    # 最后的保底
                    json_str = str(repair_json(json_str=json_str, return_objects=False))
                    result_json = json.loads(json_str)
            else:
                raise ValueError("无法解析初始设计: 未找到有效的JSON结构")

        # --- BOM 格式标准化 (Normalize) ---
        # 目标: 将所有可能的格式 (raw_list, matrix, object_list) 统一转换为 标准对象列表 list[dict]

        final_bom_list = []

        # 优先检查是否存在系统模块，若无则初始化
        if "系统模块" not in result_json:
            result_json["系统模块"] = {"模块": {}, "连接关系": []}

        # Case 1: 新的高速格式 "bom_raw_list" (字符串列表)
        if 'bom_raw_list' in result_json:
            raw_list = result_json['bom_raw_list']
            if isinstance(raw_list, list):
                for line in raw_list:
                    if isinstance(line, str):
                        parsed_item = self.parse_bom_line(line)
                        if parsed_item:
                            final_bom_list.append(parsed_item)
            # 处理完后清理字段
            del result_json['bom_raw_list']

        # Case 2: 标准格式 "bom" (可能是对象列表，也可能是模型搞错弄成了字符串列表)
        elif 'bom' in result_json:
            bom_data = result_json['bom']
            if isinstance(bom_data, list) and len(bom_data) > 0:
                # 检查列表里的元素类型
                first_item = bom_data[0]
                if isinstance(first_item, str):
                    # 模型把字符串列表放到了 'bom' 字段里 -> 解析它
                    for line in bom_data:
                        parsed_item = self.parse_bom_line(line)
                        if parsed_item:
                            final_bom_list.append(parsed_item)
                elif isinstance(first_item, dict):
                    # 已经是标准对象列表 -> 直接使用
                    final_bom_list = bom_data
                elif isinstance(first_item, list):
                    # 极其罕见：模型输出了二维数组但放在了 bom 字段 -> 当做 Matrix 处理
                    cols = ["元件ID", "型号", "零件名称", "规格描述", "单机用量", "默认供应商", "用户指定型号",
                            "用户指定品牌", "用户指定国产"]
                    for row in bom_data:
                        item = {}
                        for i, col in enumerate(cols):
                            item[col] = row[i] if i < len(row) else ""
                        final_bom_list.append(item)
            else:
                final_bom_list = []  # 空列表

        # Case 3: 旧格式 "bom_matrix" (兼容性兜底)
        elif 'bom_matrix' in result_json:
            matrix = result_json['bom_matrix']
            rows = matrix.get('rows', [])
            # 兼容处理：如果模型返回8列，则"用户指定国产"为空
            cols = ["元件ID", "型号", "零件名称", "规格描述", "单机用量", "默认供应商", "用户指定型号", "用户指定品牌",
                    "用户指定国产"]

            for row in rows:
                if not isinstance(row, list): continue
                item = {}
                # 简单的位置映射
                for i, col in enumerate(cols):
                    if i < len(row):
                        item[col] = row[i]
                    else:
                        item[col] = ""  # 缺失的列补空

                # 类型修正
                try:
                    item["单机用量"] = int(item["单机用量"]) if str(item["单机用量"]).isdigit() else 1
                except:
                    item["单机用量"] = 1

                final_bom_list.append(item)

            del result_json['bom_matrix']

        # 最终赋值
        result_json['bom'] = final_bom_list

        # 简单的完整性校验
        if not result_json['bom']:
            print("Warning: Generated BOM is empty.")

        return result_json



    def parse_bom_line(self, line_str):
        """
        [辅助方法] 智能解析单行 BOM 数据
        处理分隔符 |，自动修复列数过多或过少的情况，防止报错。
        目标列数: 9
        对应列: [元件ID, 型号, 零件名称, 规格描述, 单机用量, 默认供应商, 用户指定型号, 用户指定品牌, 用户指定国产]
        """
        # 1. 基础清理
        line = line_str.strip()
        if not line:
            return None

        # 2. 移除可能存在的 Markdown 表格边框或引号
        line = line.strip('|').strip('"').strip("'")

        # 3. 分割字符串
        parts = [p.strip() for p in line.split('|')]

        expected_cols = 9  # Updated to 9 columns
        current_cols = len(parts)

        item = {}

        # 4. 智能对齐逻辑 (Smart Alignment)
        if current_cols == expected_cols:
            # 完美情况：列数刚好
            final_parts = parts
        elif current_cols < expected_cols:
            # 缺列情况：末尾补空字符串
            # print(f"Warning: BOM line missing columns ({current_cols}/{expected_cols}). Padding with empty strings.")
            final_parts = parts + [""] * (expected_cols - current_cols)
        else:
            # 多列情况：通常是"规格描述"里包含了 |，导致被切分
            # 策略：保留头部3列(ID,型号,名称)，保留尾部5列(用量,供应商,Bool,Bool,Bool)，中间所有的都合并为规格
            # print(f"Warning: BOM line has extra columns ({current_cols}/{expected_cols}). Merging middle columns.")

            head = parts[:3]  # 前3列: ID, 型号, 名称
            tail = parts[-5:]  # 后5列: 用量, 供应商, 指定型号, 指定品牌, 国产替代
            middle = parts[3:-5]  # 中间剩余的所有内容

            merged_spec = ", ".join(middle)  # 将中间错分的列合并回规格描述
            final_parts = head + [merged_spec] + tail

        # 5. 构建字典并进行类型转换
        try:
            # 字符串字段
            item["元件ID"] = final_parts[0]
            item["型号"] = final_parts[1]
            item["零件名称"] = final_parts[2]
            item["规格描述"] = final_parts[3]

            # 数字字段 (单机用量)
            try:
                # 提取字符串中的数字，默认为1
                qty_str = final_parts[4]
                if qty_str.isdigit():
                    item["单机用量"] = int(qty_str)
                else:
                    # 处理可能存在的非数字字符
                    nums = re.findall(r'\d+', qty_str)
                    item["单机用量"] = int(nums[0]) if nums else 1
            except:
                item["单机用量"] = 1

            item["默认供应商"] = final_parts[5]

            # 布尔值字段处理
            def parse_bool(val):
                s = str(val).lower().strip()
                return s in ['true', '1', 'yes', 't', '是', 'y']

            item["用户指定型号"] = parse_bool(final_parts[6])
            item["用户指定品牌"] = parse_bool(final_parts[7])
            item["用户指定国产"] = parse_bool(final_parts[8])

            return item
        except Exception as e:
            print(f"Error parsing BOM line: {line} - {str(e)}")
            # 返回一个基础保底对象，防止整个流程崩溃
            return {
                "元件ID": parts[0] if parts else "Unknown",
                "型号": "ParseError",
                "零件名称": "Error",
                "规格描述": line_str,
                "单机用量": 1,
                "默认供应商": "",
                "用户指定型号": False,
                "用户指定品牌": False,
                "用户指定国产": False
            }

    def mapping(self, result_json, intention):
        # 1. 动态生成 ID 到 (一级模块, 二级模块) 的映射表，以及提示词用的文本列表
        # 这样可以确保代码中的常量 SECONDARY_MODULES_MAP 修改后，提示词自动更新
        id_map = {}
        prompt_lines = []
        counter = 1

        # 遍历常量构建映射
        # 注意：这里依赖全局常量 SECONDARY_MODULES_MAP
        for primary, secondaries in SECONDARY_MODULES_MAP.items():
            prompt_lines.append(f"【{primary}】:")
            for sec in secondaries:
                id_map[counter] = {"primary": primary, "secondary": sec}
                prompt_lines.append(f"{counter}. {sec}")
                counter += 1
            prompt_lines.append("")  # 空行分隔

        category_list_str = "\n".join(prompt_lines)

        # 2. 从系统模块中提取所有ID和原始名称
        module_list = self.extract_module_ids_from_system(result_json["系统模块"]["模块"])

        # 3. 准备BOM信息用于辅助判断
        bom_info = {"bom": []}
        for i in range(len(result_json['bom'])):
            tmpdata = {
                "元件ID": result_json['bom'][i]["元件ID"],
                "型号": result_json['bom'][i]["型号"],
                "零件名称": result_json['bom'][i]["零件名称"],
                "规格描述": result_json['bom'][i]["规格描述"]
            }
            bom_info['bom'].append(tmpdata)

        # 4. 准备提示词
        # 注意：这里使用了新的 template_mapping，传入了 category_list_str
        message_mapping = prompt_template_mapping.format_messages(
            module_list=json.dumps(module_list, indent=2, ensure_ascii=False),
            bom_info=json.dumps(bom_info, indent=2, ensure_ascii=False),
            category_list_str=category_list_str
        )

        savecontent = message_mapping[0].content
        with open(f'{self.output}/message_response_mapping_prompt.txt', 'w', encoding='utf-8') as f:
            f.write(savecontent)

        # 5. 调用大模型
        response_mapping = self.client.chat.completions.create(
            model=self.base_model,
            messages=[{"role": "user", "content": message_mapping[0].content}],
            max_tokens=4096,  # 减少token，因为输出全是数字
            stream=False
        )

        savecontent = response_mapping.choices[0].message.content
        with open(f'{self.output}/message_response_mapping.txt', 'w', encoding='utf-8') as f:
            f.write(savecontent)

        # 6. 解析结果
        matches_mapping = re.findall(self.json_pattern, savecontent, re.DOTALL)
        if matches_mapping:
            json_str = matches_mapping[0].strip()
            json_str = str(repair_json(json_str=json_str, return_objects=False))
            raw_mapping = json.loads(json_str)
        else:
            dict_pattern = r'(\{.*\})'
            matches_mapping = re.findall(dict_pattern, savecontent, re.DOTALL)
            if matches_mapping:
                json_str = matches_mapping[0].strip()
                json_str = str(repair_json(json_str=json_str, return_objects=False))
                raw_mapping = json.loads(json_str)
            else:
                print("映射结果解析失败，将使用默认分类")
                raw_mapping = {"mapping_ids": {}}

        # 7. 将 ID 映射回 文本名称
        # 构造符合 update_system_modules_based_on_mapping 需要的格式
        # 格式: { "ID": { "primary_module": "xxx", "secondary_module": "xxx" } }
        final_mapping_results = {}

        mapping_ids = raw_mapping.get("mapping_ids", {})

        # 遍历所有待分类的模块
        for mod in module_list:
            mod_id = mod["id"]
            original_name = mod["original_name"]

            # 获取模型返回的分类ID
            cat_id = mapping_ids.get(mod_id)

            # 转换逻辑
            if cat_id is not None and isinstance(cat_id, int) and cat_id in id_map:
                # 命中有效ID
                mapped_info = id_map[cat_id]
                final_mapping_results[mod_id] = {
                    "primary_module": mapped_info["primary"],
                    "secondary_module": mapped_info["secondary"]
                }
            else:
                # 未命中或无效ID -> 归类为一级模块‘其他’，二级模块保留原名或设为'其他'
                # 根据需求： "如果哪个器件没有结果的话就归为一级模块‘其他’"
                final_mapping_results[mod_id] = {
                    "primary_module": "其他",
                    "secondary_module": original_name  # 或者强制设为 "其他"
                }

        # 8. 更新系统模块和BOM
        if final_mapping_results:
            new_system_modules, updated_bom = self.update_system_modules_based_on_mapping(
                result_json["系统模块"]["模块"],
                final_mapping_results,
                result_json["bom"]
            )
            result_json["系统模块"]["模块"] = new_system_modules
            result_json["bom"] = updated_bom

        # 9. 最终清理和格式化（此时不需要 regen，因为 ID 来源是受控的）
        # 依然调用 correct_module_classification 以防万一有非 ID 逻辑的清理需求
        result_json = self.correct_module_classification(result_json)

        savecontent = json.dumps(result_json, indent=2, ensure_ascii=False)
        with open(f'{self.output}/test_mapping_final.txt', 'w') as f:
            f.write(savecontent)

        return result_json



    # 在类中添加新增的方法
    def extract_module_ids_from_system(self, system_modules):
        """从系统模块中提取所有ID和对应的原始名称（确保每个ID独立）"""
        module_list = []

        for primary_module, secondary_list in system_modules.items():
            for secondary_item in secondary_list:
                if '#' in secondary_item:
                    try:
                        sec_name, module_ids_str = secondary_item.split('#', 1)
                        sec_name = sec_name.strip()

                        # 拆分多个ID（如果有）
                        individual_ids = [id.strip() for id in module_ids_str.split(',')]

                        for module_id in individual_ids:
                            module_list.append({
                                "id": module_id,
                                "original_name": sec_name,
                                "original_primary": primary_module
                            })
                    except ValueError:
                        continue

        return module_list

    def chip_search(self, result_json, design_intention, max_workers=1, technical_issues=None):
        """
        芯片搜索（批量处理版），考虑设计方案需求
        """
        print('开始批量芯片搜索...')
        error_messages = ''

        # 1. 准备批量请求所需的列表容器
        titles = []
        descriptions = []
        brandassigns = []
        auto_replaces = []
        replaces = []
        domestic_subs = []  # 新增：用于存储国产替代标识的列表

        # 2. 遍历 BOM 提取参数
        for component in result_json['bom']:
            # 初始化组件状态
            component['PDF链接'] = ''
            component['价格'] = ''
            component['替代料'] = []
            component['pdfvalid'] = False
            # 备份核心参数，如果没有则使用规格描述
            component['核心参数'] = copy.deepcopy(component.get('规格描述', ''))

            # 提取参数
            name = component["型号"]
            titles.append(name)

            # 构建描述：零件名称 + 规格描述
            desc = component["零件名称"] + ' ' + component["规格描述"]
            descriptions.append(desc)

            # 处理品牌指定逻辑
            brandassign = ''
            if "用户指定品牌" in component.keys():
                if component["用户指定品牌"]:
                    brandassign = component["默认供应商"]
            brandassigns.append(brandassign)

            # 处理自动替换逻辑
            if "用户指定型号" in component:
                # 如果指定了型号，则不自动替换(False)；否则自动替换(True)
                auto_replace = not component["用户指定型号"]
            else:
                auto_replace = False
            auto_replaces.append(auto_replace)

            # 替换模式默认为 False (根据原代码逻辑)
            replaces.append(False)

            # 新增：提取用户指定国产，默认为 False，加入列表准备传入批量接口
            domestic_subs.append(component.get("用户指定国产", False))

        # 3. 调用批量搜索接口
        # 注意：这里假设 get_alternate_materials_batch 已经导入
        # 且返回的列表顺序与传入参数顺序严格一致
        st = time.time()
        search_results_list = get_alternate_materials_batch(
            titles=titles,
            descriptions=descriptions,
            ds_chat=self.client1,
            design_intention=design_intention,
            replace_list=replaces,
            auto_replace_list=auto_replaces,
            brandassign_list=brandassigns,
            domestic_sub_list=domestic_subs,  # 新增：传入国产替代参数列表
            output=self.output
        )
        print('replace耗时：%s' % (time.time() - st))

        # 4. 并行处理批量返回的结果
        def process_single_component(index, searchdata):
            """
            单个组件的处理逻辑：解析数据、更新BOM、下载PDF
            返回该组件处理过程中的错误信息（如果有）
            """
            local_error_msg = ''
            component = result_json['bom'][index]
            origin_name = titles[index]

            data = []

            # 4.1 处理匹配数据 (Match Data)
            if len(searchdata.get('match_data', {})):
                # 确保 pdfUrl 键存在
                if 'pdfUrl' not in searchdata['match_data'].keys():
                    searchdata['match_data']['pdfUrl'] = ''

                data.append(searchdata['match_data'])

                # 4.2 处理替代料数据 (Replace Data)
                replacedata = []
                replacestr = []
                # 检查 replace_data 是否存在且为列表
                raw_replace_data = searchdata.get('replace_data', [])
                if isinstance(raw_replace_data, list):
                    for item in raw_replace_data:
                        # 容错处理：确保 item 是字典且包含必要字段
                        if not isinstance(item, dict): continue

                        evaluate = item.get('evaluate', '')
                        item_data = item.get('replace_data', {})

                        replacetitle = item_data.get("title", "")
                        brandNameCn = item_data.get("brandNameCn", "")

                        unique_key = ''.join([replacetitle, brandNameCn])
                        if unique_key not in replacestr and replacetitle:
                            replacedata.append({
                                'evaluate': evaluate,
                                'replacetitle': replacetitle,
                                'brandNameCn': brandNameCn
                            })
                            replacestr.append(unique_key)

                component['替代料'] = replacedata
            else:
                component['默认供应商'] = ''

            # 4.3 后处理：更新组件信息、下载PDF、验证
            if len(data):
                bestindex = 0
                match_item = data[bestindex]

                pdfurl = match_item.get('pdfUrl', '')

                new_name = match_item.get('title', origin_name)
                name_std = re.sub(r'[^a-zA-Z0-9]', '', new_name)
                save_path = f'{self.output}/{name_std}.pdf'

                # 更新组件基础信息
                component['默认供应商'] = match_item.get('brandNameCn', '')
                component['型号'] = new_name

                # 更新核心参数
                # 逻辑：先重置为原始规格描述，如果有新的xcl核心参数则覆盖
                component['核心参数'] = copy.deepcopy(component.get('规格描述', ''))
                if match_item.get('xcl核心参数'):
                    component['规格描述'] = match_item['xcl核心参数']

                # PDF 下载与验证
                validflag = 1

                # 尝试下载
                download_success = False
                if pdfurl:
                    try:
                        download_success = download_pdf(pdfurl, save_path)
                    except Exception as e:
                        print(f"下载PDF出错 {new_name}: {e}")
                        download_success = False

                if download_success:
                    # 验证PDF
                    try:
                        pdfvalid = is_pdf_valid(save_path)
                    except Exception:
                        pdfvalid = False

                    if pdfvalid:
                        component['PDF链接'] = pdfurl
                        component['pdfvalid'] = True
                        validflag = 0

                if validflag:
                    local_error_msg += '%s:PDF链接失效，需重新确定其对应的datasheet链接。\n' % new_name
            else:
                local_error_msg += '%s:型号可能不存在，需进行型号验证或者替换\n' % origin_name

            # 注意：此处并未对 component['用户指定国产'] 进行修改，因此原值被保留

            return local_error_msg

        # 使用线程池并行处理后续逻辑（主要是并行化下载PDF）
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 提交所有任务
            futures = [
                executor.submit(process_single_component, index, searchdata)
                for index, searchdata in enumerate(search_results_list)
            ]

            # 收集结果
            for future in as_completed(futures):
                try:
                    msg = future.result()
                    error_messages += msg
                except Exception as e:
                    print(f"处理组件结果时发生未捕获异常: {e}")

        print("所有元件批量处理完成")
        return result_json

    def _extract_circuits_parallel(self, bom_list, max_workers=10):
        starttime = time.time()
        allnames = []
        tcgimgs = {}
        for comp in bom_list:
            pdfurl = comp['PDF链接']
            name = comp['型号']
            name_std = re.sub(r'[^a-zA-Z0-9]', '', name)
            if not pdfurl:
                continue

            save_path = f'{self.output}/{name_std}.pdf'
            abs_path = str(Path(save_path).resolve())
            if comp['pdfvalid']:
                payload = {"pdf_path": abs_path, "name": name_std}
                try:
                    response = requests.post("http://localhost:5000/execute", json=payload)
                    if response.ok:
                        image_paths = response.json().get("image_paths", [])
                        if image_paths and name not in allnames:
                            tcgimgs[name] = image_paths[0]
                            allnames.append(name)
                except Exception as e:
                    print(f"电路图提取失败 {name}: {str(e)}")
        return tcgimgs

    def updatadesign(self, result_json, intention):
        """
        优化版方案描述生成：
        使用竖线分隔的字符串列表代替对象列表，大幅减少Token占用。
        """
        # 定义需要过滤的低价值器件关键词（阻容感、连接器、结构件等）
        ignore_keywords = [
            '电阻', '电容', '电感', '磁珠', '跳线', '排针', '排母', '连接器', '插座', '开关',
            'Resistor', 'Capacitor', 'Inductor', 'Bead', 'Connector', 'Header', 'Socket', 'Switch',
            'Screw', 'Nut', 'Washer', 'PCB'
        ]

        # 1. 构建精简版上下文 (Lean Context) - 转换为 "Raw List" 格式
        lean_bom_list = []

        # 添加表头帮助模型理解列对应关系（可选，消耗极少Token但能提升准确度）
        # 格式: 零件名称 | 型号 | 规格描述 | 品牌

        for item in result_json['bom']:
            part_name = item.get("零件名称", "Unknown")

            # 策略A: 过滤掉不需要出现在方案描述中的辅助器件
            # 如果项目比较大，建议开启此过滤；如果项目很小，可以注释掉
            # if any(k in part_name for k in ignore_keywords):
            #     continue

            model = item.get("型号", "N/A")
            brand = item.get("默认供应商", "")

            # 获取规格，优先核心参数
            spec = item.get("核心参数") or item.get("规格描述", "")
            if spec:
                # 截断过长的规格描述
                if len(spec) > 60:
                    spec = spec[:60] + "..."
                # 清洗：移除内容中的竖线，避免分隔符冲突
                spec = spec.replace("|", "/")
                spec = spec.replace("\n", " ")
            else:
                spec = ""

            # 拼接成字符串
            line = f"{part_name} | {model} | {spec} | {brand}"
            lean_bom_list.append(line)

        # 如果过滤后BOM为空（极端情况），回退保留前10个重要组件
        if not lean_bom_list and result_json['bom']:
            for item in result_json['bom'][:10]:
                spec = (item.get("核心参数") or item.get("规格描述", ""))[:60].replace("|", "/")
                line = f"{item['零件名称']} | {item['型号']} | {spec} | {item.get('默认供应商', '')}"
                lean_bom_list.append(line)

        # 2. 构建精简设计对象
        lean_design = {
            "Structure": result_json.get("系统模块", {}),  # 系统架构图数据
            "KeyComponents": lean_bom_list  # 压缩后的字符串列表
        }

        # 转换为JSON字符串
        # separators=(',', ':') 去除 key-value 之间的空格，极致压缩 Token
        lean_design_str = json.dumps(lean_design, ensure_ascii=False, separators=(',', ':'))

        # 3. 格式化提示词
        # 注意：这里需要重新从全局获取 template_update，确保使用了上面更新后的模板
        prompt_template_update_optimized = ChatPromptTemplate.from_template(template_update)
        message_update = prompt_template_update_optimized.format_messages(
            intention=intention,
            current_design=lean_design_str
        )

        # 4. 调试记录 (可选)
        try:
            with open(f'{self.output}/message_update_prompt.txt', 'w', encoding='utf-8') as f:
                f.write(message_update[0].content)
        except Exception:
            pass

        # 5. 调用大模型
        try:
            response_update = self.client.chat.completions.create(
                model=self.base_model,
                messages=[
                    {"role": "user", "content": message_update[0].content},
                ],
                max_tokens=4000,
                stream=False
            )
            savecontent = response_update.choices[0].message.content

            # 调试记录
            try:
                with open(f'{self.output}/message_update.txt', 'w', encoding='utf-8') as f:
                    f.write(savecontent)
            except Exception:
                pass

            # 6. 健壮的JSON解析
            try:
                result_json_update = json.loads(savecontent)
            except json.JSONDecodeError:
                # 尝试正则提取 JSON
                matches_system = re.findall(self.json_pattern, savecontent, re.DOTALL)
                if matches_system:
                    json_str = matches_system[0].strip()
                else:
                    # 备用正则：寻找最外层大括号
                    dict_pattern = r'(\{.*\})'
                    matches_system = re.findall(dict_pattern, savecontent, re.DOTALL)
                    if matches_system:
                        json_str = matches_system[0].strip()
                    else:
                        print("Warning: Failed to parse JSON description, using raw text.")
                        return {"方案描述": savecontent}

                # 使用 json_repair 修复可能的不规范 JSON
                json_str = str(repair_json(json_str=json_str, return_objects=False))
                result_json_update = json.loads(json_str)

            return result_json_update

        except Exception as e:
            print(f"Update design failed: {e}")
            return {"方案描述": "方案描述生成失败，请稍后重试。"}

    def selective_chip_search(self, new_design, old_design, design_intention, max_workers=1,
                              key_fields=["零件名称", "默认供应商", "用户指定型号", "用户指定品牌", "用户指定国产"]):
        """选择性芯片搜索 - 只搜索新增或修改的组件"""
        print("开始选择性芯片搜索...")

        # 创建旧BOM的映射
        old_bom_map = {comp["型号"]: comp for comp in old_design['bom']}
        new_components = []

        # 识别需要搜索的新组件
        for comp in new_design['bom']:
            model = comp["型号"]
            if model not in old_bom_map:
                # 新组件，需要搜索
                new_components.append(comp)
            else:
                old_comp = old_bom_map[model]
                # 检查关键字段是否发生变化
                if any(comp.get(field) != old_comp.get(field) for field in key_fields):
                    # 关键字段发生变化，需要重新搜索
                    new_components.append(comp)
                else:
                    # 组件没有变化，复用旧数据
                    comp.update({
                        "PDF链接": old_comp.get("PDF链接", ""),
                        "价格": old_comp.get("价格", ""),
                        "替代料": old_comp.get("替代料", []),
                        "pdfvalid": old_comp.get("pdfvalid", False),
                        "核心参数": old_comp.get("核心参数", "")
                    })
                    comp["规格描述"] = old_comp.get("规格描述", "")

        # 只对新组件进行芯片搜索
        if new_components:
            print(f'需要更新的组件数量: {len(new_components)}')
            temp_design = copy.deepcopy(new_design)
            temp_design['bom'] = new_components
            # print(temp_design['bom'],1111111111111111111)
            # print(design_intention)
            # 执行芯片搜索
            updated_components = self.chip_search(temp_design, design_intention, max_workers)['bom']
            # print(updated_components,22222222222222222)
            # 修复：使用元件ID而不是型号名称作为匹配键
            updated_map = {comp["元件ID"]: comp for comp in updated_components}
            for i, comp in enumerate(new_design['bom']):
                if comp["元件ID"] in updated_map:
                    new_design['bom'][i] = updated_map[comp["元件ID"]]

            print(f"选择性芯片搜索完成，更新了 {len(updated_components)} 个组件")
        else:
            print("没有需要更新的组件，跳过芯片搜索")

        return new_design


    def noBaseGenerate(self, intention):
        # System Generation ####
        starttime_f = time.time()
        self.intention = intention

        print('System generating...')
        result_json = self.system_gen( intention)
        print('耗时：%s' % (time.time() - starttime_f))
        # BOM表合并
        boms = copy.deepcopy(result_json['bom'])
        df = pd.DataFrame(boms)

        # 1. 预处理：填充空值，防止 groupby 时因为 NaN 导致数据丢失
        cols_to_fill = ['型号', '零件名称', '规格描述', '默认供应商']
        for col in cols_to_fill:
            if col in df.columns:
                df[col] = df[col].fillna('')

        # 2. 修改分组逻辑：使用 [型号, 零件名称, 规格描述] 联合分组
        # 这样可以区分同为"国产替代型号"但功能不同的器件
        out = (df.groupby(['型号', '零件名称', '规格描述'], as_index=False)
               .agg({'元件ID': ','.join,
                     '单机用量': 'sum',
                     # 注意：零件名称和规格描述已作为分组键，此处不需要再聚合
                     '默认供应商': 'first',
                     '用户指定型号': 'first',
                     '用户指定品牌': 'first',
                     '用户指定国产': 'first'}))

        new_bom = out.to_dict('records')
        result_json['bom'] = new_bom
        rawdesign = copy.deepcopy(result_json)
        # chip search####
        starttime = time.time()
        print('Chip searching...')
        result_json = self.chip_search(result_json, intention, max_workers=50)
        print('耗时：%s' % (time.time() - starttime))


        # mapping
        print("开始模块映射...")
        starttime = time.time()
        result_json = self.mapping(result_json, intention)
        print('mapping耗时：%s' % (time.time() - starttime))


        print('开始并行任务：更新方案描述 & 提取电路图...')
        starttime_parallel = time.time()
        design_modified = 1
        tcgimgs = {}

        with ThreadPoolExecutor(max_workers=2) as executor:
            # 任务1：更新方案描述
            future_desc = None
            if design_modified:
                future_desc = executor.submit(self.updatadesign, result_json, intention)
            future_imgs = executor.submit(self._extract_circuits_parallel, result_json['bom'])
            if future_desc:
                try:
                    desc_result_start = time.time()
                    result_json_update = future_desc.result()
                    result_json['方案描述'] = result_json_update['方案描述']
                    desc_result_end = time.time()
                    print(f"获取方案描述结果耗时: {desc_result_end - desc_result_start:.2f}秒")
                except Exception as e:
                    print(f"并行更新方案描述失败: {e}")

            try:
                imgs_result_start = time.time()
                tcgimgs = future_imgs.result()
                imgs_result_end = time.time()
                print(f"获取电路图结果耗时: {imgs_result_end - imgs_result_start:.2f}秒")
            except Exception as e:
                print(f"并行提取电路图失败: {e}")
                tcgimgs = {}

        print('并行任务总耗时：%s' % (time.time() - starttime_parallel))
        starttime = time.time()
        blockdata = copy.deepcopy(result_json['系统模块'])
        # sys block
        _, img_path, _ = mermaid_to_graphviz(
            blockdata,
            output_path=f'{self.output}/apply_system',
            node_border_style='dashed',
            subgraph_border_style='dashed',
            xlabel_fontsize=7,
            font_family='SimHei',
            vertical_label_rotation=90,  # 垂直边标签旋转90度
            horizontal_label_rotation=0  # 水平边标签不旋转
        )
        _, _ = generate_nine_grid(
            blockdata['模块'],
            f"{self.output}/block_system",
            base_cell_width=300,  # 基础单元格宽度
            base_cell_height=300,  # 基础单元格高度
            horizontal_gap=30,  # 水平间隙
            vertical_gap=25,  # 垂直间隙
            title_font_size=38,  # 标题字体大小
            node_font_size=32,  # 节点字体大小
            node_gap=15,  # 节点之间的垂直间隙
            background_color="#ffffff",  # 设置背景颜色
            empty_color="#ebe8e7",  # 自定义空模块背景色
            node_box_height=50,  # 节点框高度
            node_box_width_ratio=0.85
        )
        image_path = f'{self.output}/block_system.png'
        with open(image_path, 'rb') as img_file:
            image_data = base64.b64encode(img_file.read()).decode('utf-8')
        drawio_path = f'{self.output}/block_system.drawio'
        with open(drawio_path, 'r', encoding='utf-8') as drawio_file:
            drawio_content = drawio_file.read()
        image_id = str(uuid.uuid4())
        print('布局耗时：%s' % (time.time() - starttime))
        result_json['方案描述'] = remove_citations(result_json['方案描述'])
        generated_data = {
            "框图": {
                "data": image_data,
                "id": image_id,
                "mime": "image/png",
                "drawio_xml": drawio_content
            },
            "bom": result_json['bom'],
            "方案描述": result_json['方案描述'] + '\n----------------\n',  # +analysis_report,
            'circuit_paths': tcgimgs,
            'system_block': result_json['系统模块'],
            "替代料": "正在开发中"
        }
        self.generatedata = result_json
        # self.intention = intention
        print('总耗时：%s' % (time.time() - starttime_f))
        return generated_data

    def multiGenerate(self, message, conversation_history_test):
        start_f = time.time()
        print(f"开始处理修改请求: {message}")

        # 如果没有现有数据，则直接调用noBaseGenerate
        if not hasattr(self, 'generatedata') or not self.generatedata:
            print("没有现有设计数据，使用noBaseGenerate创建新设计")
            return self.noBaseGenerate(message)

        # --- Step 1: 压缩 Input Context (Dict -> Raw List String) ---
        # 将现有的 BOM 对象列表转换为字符串列表，减少 Token 消耗
        current_bom_raw = []
        for item in self.generatedata['bom']:
            # 规格描述防错处理：移除可能存在的竖线
            spec = str(item.get("核心参数") or item.get("规格描述", "")).replace("|", ",")

            # 更新：加入 "用户指定国产" 字段 (第9列)
            line = (f"{item.get('元件ID', '')} | {item.get('型号', '')} | {item.get('零件名称', '')} | "
                    f"{spec} | {item.get('单机用量', 1)} | {item.get('默认供应商', '')} | "
                    f"{str(item.get('用户指定型号', False)).lower()} | {str(item.get('用户指定品牌', False)).lower()} | "
                    f"{str(item.get('用户指定国产', False)).lower()}")
            current_bom_raw.append(line)

        # 构建压缩后的设计对象 (去除方案描述等冗余信息)
        currentdesign_compressed = {
            "系统模块": self.generatedata["系统模块"],
            "bom_raw_list": current_bom_raw
        }
        currentdesign_str = json.dumps(currentdesign_compressed, ensure_ascii=False)

        # --- Step 2: 调用大模型 ---
        message_multi = prompt_template_multi.format_messages(
            intention=self.intention,
            currentdesign=currentdesign_str,
            message=message
        )

        # 调试保存 Prompt
        savecontent = message_multi[0].content
        with open(f'{self.output}/message_modification_prompt.txt', 'w', encoding='utf-8') as f:
            f.write(savecontent)

        response_multi = self.client.chat.completions.create(
            model=self.base_model,
            messages=[{"role": "user", "content": message_multi[0].content}],
            max_tokens=8000,
            stream=False
        )

        savecontent = response_multi.choices[0].message.content
        with open(f'{self.output}/message_modification.txt', 'w', encoding='utf-8') as f:
            f.write(savecontent)

        # --- Step 3: 解析 JSON 和 还原 BOM ---
        try:
            matches = re.findall(self.json_pattern, savecontent, re.DOTALL)
            if not matches:
                matches = re.findall(r'(\{.*\})', savecontent, re.DOTALL)

            if matches:
                json_str = matches[0].strip()
                json_str = str(repair_json(json_str=json_str, return_objects=False))
                modified_design = json.loads(json_str)
            else:
                raise ValueError("无法解析返回的JSON")

            # 关键步骤：解析 bom_raw_list 回到 list[dict]
            final_bom_list = []

            # 优先处理 raw_list
            if 'bom_raw_list' in modified_design:
                for line in modified_design['bom_raw_list']:
                    if isinstance(line, str):
                        # 复用类中已有的 parse_bom_line 方法 (已支持9列)
                        parsed_item = self.parse_bom_line(line)
                        if parsed_item:
                            final_bom_list.append(parsed_item)
                del modified_design['bom_raw_list']  # 清理掉中间字段

            # 兼容处理（万一模型还是回了 bom 对象列表）
            elif 'bom' in modified_design and isinstance(modified_design['bom'], list):
                if len(modified_design['bom']) > 0 and isinstance(modified_design['bom'][0], str):
                    for line in modified_design['bom']:
                        parsed_item = self.parse_bom_line(line)
                        if parsed_item:
                            final_bom_list.append(parsed_item)
                else:
                    final_bom_list = modified_design['bom']

            modified_design['bom'] = final_bom_list

        except Exception as e:
            print(f"解析修改后的设计失败: {e}")
            # 如果解析失败，回退到原始数据防止崩溃，但抛出错误信息
            return self.generatedata

        # --- Step 4: 后续流程 (芯片搜索、电路图、文档更新) ---

        print('开始芯片搜索...')
        starttime = time.time()
        # multi_intention = self.intention + '\n用户的新的需求如下：%s' % message
        # multi_intention = '【用户原始需求】\n'  + self.intention+'\n【用户的修改需求】\n%s' % message
        # if self.history == 0:
        #     multi_intention = '【用户原始需求】\n'  + self.intention+'\n【历史修改记录（供参考）】\n%s.%s' % (self.history,message)
        # else:
        #     multi_intention = self.intention + '\n%s.%s' % (self.history, message)


        multi_intention = self.intention + '\n %s'  %message
        original_design = copy.deepcopy(self.generatedata)
        self.history+=1
        # 执行选择性芯片搜索 (只搜索变动的)
        # print(modified_design,111111111)
        # print(original_design, 111111111)
        # 更新：key_fields 包含 "用户指定国产"
        modified_design = self.selective_chip_search(
            modified_design,
            original_design,
            multi_intention,
            max_workers=50,
            key_fields=["零件名称", "默认供应商", "用户指定型号", "用户指定品牌",  "用户指定国产"]
        )

        # 合并bom (Aggregation)
        boms = copy.deepcopy(modified_design['bom'])
        if boms:
            df = pd.DataFrame(boms)
            # 确保列存在防止报错
            cols_to_check = ['元件ID', '型号', '零件名称', '规格描述', '单机用量', '默认供应商', '用户指定型号',
                             '用户指定品牌', '用户指定国产', 'PDF链接', '价格', 'pdfvalid', '核心参数']
            for col in cols_to_check:
                if col not in df.columns:
                    # 数值型给0，字符型给空
                    if col in ['单机用量']:
                        df[col] = 0
                    else:
                        df[col] = ""
                else:
                    # 填充 NaN
                    if col not in ['单机用量']:
                        df[col] = df[col].fillna("")

            # 修改分组逻辑：同样加入 零件名称 和 规格描述
            out = (df.groupby(['型号', '零件名称', '规格描述'], as_index=False)
                   .agg({'元件ID': ','.join,
                         '单机用量': 'sum',
                         # '零件名称': 'first', # 已作为Key
                         # '规格描述': 'first', # 已作为Key
                         '默认供应商': 'first',
                         '用户指定型号': 'first',
                         '用户指定品牌': 'first',
                         '用户指定国产': 'first',
                         'PDF链接': 'first',  # 保留已有数据
                         '价格': 'first',
                         'pdfvalid': 'first',
                         '核心参数': 'first'}))
            new_bom = out.to_dict('records')
            modified_design['bom'] = new_bom

        print('芯片搜索耗时：%s' % (time.time() - starttime))


        # 更新方案描述和系统模块 (并行)
        print('开始并行任务：更新方案描述 & 提取电路图...')
        starttime_parallel = time.time()
        tcgimgs = {}

        with ThreadPoolExecutor(max_workers=2) as executor:
            future_desc = executor.submit(self.updatadesign, modified_design, multi_intention)
            future_imgs = executor.submit(self._extract_circuits_parallel, modified_design['bom'])

            try:
                updated_design = future_desc.result()
                modified_design['方案描述'] = updated_design.get('方案描述', '')
            except Exception as e:
                print(f"更新方案描述失败: {e}")

            try:
                tcgimgs = future_imgs.result()
            except Exception as e:
                print(f"提取电路图失败: {e}")

        print('并行任务总耗时：%s' % (time.time() - starttime_parallel))

        # --- Step 5: 生成可视化 (Mermaid/NineGrid) ---
        blockdata = copy.deepcopy(modified_design['系统模块'])
        _, img_path, _ = mermaid_to_graphviz(
            blockdata,
            output_path=f'{self.output}/apply_system',
            node_border_style='dashed',
            subgraph_border_style='dashed',
            xlabel_fontsize=7,
            font_family='SimHei',
            vertical_label_rotation=90,
            horizontal_label_rotation=0
        )
        _, _ = generate_nine_grid(
            blockdata['模块'],
            f"{self.output}/block_system",
            base_cell_width=300,
            base_cell_height=300,
            horizontal_gap=30,
            vertical_gap=25,
            title_font_size=38,
            node_font_size=32,
            node_gap=15,
            background_color="#ffffff",
            empty_color="#ebe8e7",
            node_box_height=50,
            node_box_width_ratio=0.85
        )
        image_path = f'{self.output}/block_system.png'
        with open(image_path, 'rb') as img_file:
            image_data = base64.b64encode(img_file.read()).decode('utf-8')
        drawio_path = f'{self.output}/block_system.drawio'
        with open(drawio_path, 'r', encoding='utf-8') as drawio_file:
            drawio_content = drawio_file.read()
        image_id = str(uuid.uuid4())

        if '方案描述' in modified_design:
            modified_design['方案描述'] = remove_citations(modified_design['方案描述'])

        generated_data = {
            "框图": {
                "data": image_data,
                "id": image_id,
                "mime": "image/png",
                "drawio_xml": drawio_content
            },
            "bom": modified_design['bom'],
            "方案描述": modified_design.get('方案描述', ''),
            'circuit_paths': tcgimgs,
            'system_block': modified_design['系统模块'],
            "替代料": "正在开发中"
        }
        self.generatedata = modified_design
        self.intention = multi_intention
        print('修改总耗时：%s' % (time.time() - start_f))
        return generated_data