"""
RAG专家知识库检索模块
用于从历史方案数据中检索相似方案，辅助LLM生成新方案
"""

import json
import os
from typing import List, Dict, Optional, Any
from langchain_community.vectorstores import FAISS
from langchain.schema import Document
import logging

logger = logging.getLogger(__name__)


def build_searchable_text(case_data: Dict) -> str:
    """
    将结构化方案数据转换为可检索的文本
    
    Args:
        case_data: 单个方案的数据字典
        
    Returns:
        可检索的文本字符串
    """
    text_parts = []
    
    # 1. 项目基本信息
    project_name = case_data.get('crmPjProjectIdName', '')
    if project_name:
        text_parts.append(f"项目名称: {project_name}")
    
    project_domain = case_data.get('otherProjectSegmentsName', '')
    if project_domain:
        # 提取主要领域（取第一个分类）
        main_domain = project_domain.split(',')[0].split('(')[0] if project_domain else ''
        if main_domain:
            text_parts.append(f"应用领域: {main_domain}")
    
    customer_product = case_data.get('customerProductName', '')
    if customer_product:
        text_parts.append(f"客户产品: {customer_product}")
    
    # 2. 电源模块信息（三级电源架构）
    power_info = []
    if case_data.get('sourceOne'):
        power_info.append(f"一级电源: {case_data['sourceOne']}")
    if case_data.get('sourceOneInside') and case_data.get('sourceOneInside') != 'NA':
        power_info.append(f"一级电源内部: {case_data['sourceOneInside']}")
    
    if case_data.get('sourceTwo'):
        power_info.append(f"二级电源: {case_data['sourceTwo']}")
    if case_data.get('sourceTwoInside') and case_data.get('sourceTwoInside') != 'NA':
        power_info.append(f"二级电源内部: {case_data['sourceTwoInside']}")
    
    if case_data.get('sourceThree'):
        power_info.append(f"三级电源: {case_data['sourceThree']}")
    if case_data.get('sourceThreeInside') and case_data.get('sourceThreeInside') != 'NA':
        power_info.append(f"三级电源内部: {case_data['sourceThreeInside']}")
    
    if case_data.get('sourceDes') and case_data.get('sourceDes') != 'NA':
        power_info.append(f"电源描述: {case_data['sourceDes']}")
    
    if power_info:
        text_parts.append("电源模块: " + ", ".join(power_info))
    
    # 3. 主控信息
    master_control_info = []
    if case_data.get('masterControl'):
        master_control_info.append(f"主控系列: {case_data['masterControl']}")
    if case_data.get('masterControlInside') and case_data.get('masterControlInside') != 'NA':
        master_control_info.append(f"主控型号: {case_data['masterControlInside']}")
    if case_data.get('masterControlDes'):
        master_control_info.append(f"主控描述: {case_data['masterControlDes']}")
    if master_control_info:
        text_parts.append("主控模块: " + ", ".join(master_control_info))
    
    # 4. 信号采集链
    signal_chain = []
    if case_data.get('signalInput'):
        signal_chain.append(f"信号输入: {case_data['signalInput']}")
    if case_data.get('signalInputInside') and case_data.get('signalInputInside') != 'NA':
        signal_chain.append(f"信号输入内部: {case_data['signalInputInside']}")
    
    if case_data.get('amplifier'):
        signal_chain.append(f"放大器: {case_data['amplifier']}")
    if case_data.get('amplifierInside') and case_data.get('amplifierInside') != 'NA':
        signal_chain.append(f"放大器内部: {case_data['amplifierInside']}")
    
    if case_data.get('adc'):
        signal_chain.append(f"ADC: {case_data['adc']}")
    if case_data.get('adcInside') and case_data.get('adcInside') != 'NA':
        signal_chain.append(f"ADC内部: {case_data['adcInside']}")
    
    if case_data.get('signalDes') and case_data.get('signalDes') != 'NA':
        signal_chain.append(f"信号描述: {case_data['signalDes']}")
    
    if signal_chain:
        text_parts.append("信号采集模块: " + " → ".join(signal_chain))
    
    # 5. 存储模块
    storage_info = []
    if case_data.get('storage'):
        storage_info.append(f"存储: {case_data['storage']}")
    if case_data.get('storageInside') and case_data.get('storageInside') != 'NA':
        storage_info.append(f"存储内部: {case_data['storageInside']}")
    if case_data.get('storageDes'):
        storage_info.append(f"存储描述: {case_data['storageDes']}")
    if storage_info:
        text_parts.append("存储模块: " + ", ".join(storage_info))
    
    # 6. 通信接口
    comm_info = []
    if case_data.get('communication'):
        comm_info.append(f"通信接口: {case_data['communication']}")
    if case_data.get('communicationInside') and case_data.get('communicationInside') != 'NA':
        comm_info.append(f"通信内部: {case_data['communicationInside']}")
    if case_data.get('communicationDes'):
        comm_info.append(f"通信描述: {case_data['communicationDes']}")
    if comm_info:
        text_parts.append("通信接口模块: " + ", ".join(comm_info))
    
    # 7. 时钟模块
    clock_info = []
    if case_data.get('clock'):
        clock_info.append(f"时钟: {case_data['clock']}")
    if case_data.get('clockInside') and case_data.get('clockInside') != 'NA':
        clock_info.append(f"时钟内部: {case_data['clockInside']}")
    if case_data.get('clockDes'):
        clock_info.append(f"时钟描述: {case_data['clockDes']}")
    if clock_info:
        text_parts.append("时钟模块: " + ", ".join(clock_info))
    
    # 8. 人机界面
    hmi_info = []
    if case_data.get('hmi'):
        hmi_info.append(f"人机界面: {case_data['hmi']}")
    if case_data.get('hmiInside') and case_data.get('hmiInside') != 'NA':
        hmi_info.append(f"人机界面内部: {case_data['hmiInside']}")
    if case_data.get('hmiDes'):
        hmi_info.append(f"人机界面描述: {case_data['hmiDes']}")
    if hmi_info:
        text_parts.append("人机界面模块: " + ", ".join(hmi_info))
    
    # 9. 控制驱动
    control_info = []
    if case_data.get('controlDrive'):
        control_info.append(f"控制驱动: {case_data['controlDrive']}")
    if case_data.get('controlDriveInside') and case_data.get('controlDriveInside') != 'NA':
        control_info.append(f"控制驱动内部: {case_data['controlDriveInside']}")
    if case_data.get('controlDriveDes'):
        control_info.append(f"控制驱动描述: {case_data['controlDriveDes']}")
    if control_info:
        text_parts.append("控制驱动模块: " + ", ".join(control_info))
    
    # 10. 其他模块
    other_info = []
    if case_data.get('other'):
        other_info.append(f"其他: {case_data['other']}")
    if case_data.get('otherInside') and case_data.get('otherInside') != 'NA':
        other_info.append(f"其他内部: {case_data['otherInside']}")
    if case_data.get('otherDes'):
        other_info.append(f"其他描述: {case_data['otherDes']}")
    if other_info:
        text_parts.append("其他模块: " + ", ".join(other_info))
    
    return "\n".join(text_parts)


def extract_module_details(case_data: Dict) -> Dict[str, Dict]:
    """
    从方案数据中提取模块详细信息
    
    Args:
        case_data: 方案数据字典
        
    Returns:
        模块详细信息字典
    """
    modules = {}
    
    # 电源模块
    power_external = []
    power_internal = []
    if case_data.get('sourceOne'):
        power_external.append(case_data['sourceOne'])
    if case_data.get('sourceTwo'):
        power_external.append(case_data['sourceTwo'])
    if case_data.get('sourceThree'):
        power_external.append(case_data['sourceThree'])
    
    if case_data.get('sourceOneInside') and case_data.get('sourceOneInside') != 'NA':
        power_internal.append(case_data['sourceOneInside'])
    if case_data.get('sourceTwoInside') and case_data.get('sourceTwoInside') != 'NA':
        power_internal.append(case_data['sourceTwoInside'])
    if case_data.get('sourceThreeInside') and case_data.get('sourceThreeInside') != 'NA':
        power_internal.append(case_data['sourceThreeInside'])
    
    if power_external or power_internal or (case_data.get('sourceDes') and case_data.get('sourceDes') != 'NA'):
        modules['电源'] = {
            'description': case_data.get('sourceDes', '') if case_data.get('sourceDes') != 'NA' else '',
            'external_parts': power_external,
            'internal_parts': power_internal
        }
    
    # 信号采集模块
    signal_external = []
    signal_internal = []
    if case_data.get('signalInput'):
        signal_external.append(case_data['signalInput'])
    if case_data.get('amplifier'):
        signal_external.append(case_data['amplifier'])
    if case_data.get('adc'):
        signal_external.append(case_data['adc'])
    
    if case_data.get('signalInputInside') and case_data.get('signalInputInside') != 'NA':
        signal_internal.append(case_data['signalInputInside'])
    if case_data.get('amplifierInside') and case_data.get('amplifierInside') != 'NA':
        signal_internal.append(case_data['amplifierInside'])
    if case_data.get('adcInside') and case_data.get('adcInside') != 'NA':
        signal_internal.append(case_data['adcInside'])
    
    if signal_external or signal_internal or (case_data.get('signalDes') and case_data.get('signalDes') != 'NA'):
        modules['信号采集'] = {
            'description': case_data.get('signalDes', '') if case_data.get('signalDes') != 'NA' else '',
            'external_parts': signal_external,
            'internal_parts': signal_internal
        }
    
    # 主控模块
    if case_data.get('masterControl') or (case_data.get('masterControlInside') and case_data.get('masterControlInside') != 'NA'):
        modules['主控'] = {
            'description': case_data.get('masterControlDes', ''),
            'external_parts': [case_data['masterControl']] if case_data.get('masterControl') else [],
            'internal_parts': [case_data['masterControlInside']] if case_data.get('masterControlInside') and case_data.get('masterControlInside') != 'NA' else []
        }
    
    # 存储模块
    if case_data.get('storage') or (case_data.get('storageInside') and case_data.get('storageInside') != 'NA'):
        modules['存储'] = {
            'description': case_data.get('storageDes', ''),
            'external_parts': [case_data['storage']] if case_data.get('storage') else [],
            'internal_parts': [case_data['storageInside']] if case_data.get('storageInside') and case_data.get('storageInside') != 'NA' else []
        }
    
    # 通信接口模块
    if case_data.get('communication') or (case_data.get('communicationInside') and case_data.get('communicationInside') != 'NA'):
        comm_external = []
        comm_internal = []
        if case_data.get('communication'):
            # 可能是逗号分隔的多个接口
            comm_external = [c.strip() for c in case_data['communication'].split(',')]
        if case_data.get('communicationInside') and case_data.get('communicationInside') != 'NA':
            comm_internal = [case_data['communicationInside']]
        
        modules['通信和接口'] = {
            'description': case_data.get('communicationDes', ''),
            'external_parts': comm_external,
            'internal_parts': comm_internal
        }
    
    # 时钟模块
    if case_data.get('clock') or (case_data.get('clockInside') and case_data.get('clockInside') != 'NA'):
        modules['时钟'] = {
            'description': case_data.get('clockDes', ''),
            'external_parts': [case_data['clock']] if case_data.get('clock') else [],
            'internal_parts': [case_data['clockInside']] if case_data.get('clockInside') and case_data.get('clockInside') != 'NA' else []
        }
    
    # 人机界面模块
    if case_data.get('hmi') or (case_data.get('hmiInside') and case_data.get('hmiInside') != 'NA'):
        modules['人机界面'] = {
            'description': case_data.get('hmiDes', ''),
            'external_parts': [case_data['hmi']] if case_data.get('hmi') else [],
            'internal_parts': [case_data['hmiInside']] if case_data.get('hmiInside') and case_data.get('hmiInside') != 'NA' else []
        }
    
    # 控制驱动模块
    if case_data.get('controlDrive') or (case_data.get('controlDriveInside') and case_data.get('controlDriveInside') != 'NA'):
        modules['控制驱动'] = {
            'description': case_data.get('controlDriveDes', ''),
            'external_parts': [case_data['controlDrive']] if case_data.get('controlDrive') else [],
            'internal_parts': [case_data['controlDriveInside']] if case_data.get('controlDriveInside') and case_data.get('controlDriveInside') != 'NA' else []
        }
    
    # 其他模块
    if case_data.get('other') or (case_data.get('otherInside') and case_data.get('otherInside') != 'NA'):
        modules['其他'] = {
            'description': case_data.get('otherDes', ''),
            'external_parts': [case_data['other']] if case_data.get('other') else [],
            'internal_parts': [case_data['otherInside']] if case_data.get('otherInside') and case_data.get('otherInside') != 'NA' else []
        }
    
    return modules


class RAGRetriever:
    """RAG检索器类"""
    
    def __init__(self, vectorstore: FAISS, data_path: str):
        """
        初始化RAG检索器
        
        Args:
            vectorstore: FAISS向量存储对象
            data_path: 原始数据文件路径（用于获取完整信息）
        """
        self.vectorstore = vectorstore
        self.data_path = data_path
        self.cases_dict = {}
        
        # 预加载原始数据
        self._load_cases_dict()
    
    def _load_cases_dict(self):
        """加载原始数据到字典，以ID为键"""
        try:
            with open(self.data_path, 'r', encoding='utf-8') as f:
                cases = json.load(f)
                self.cases_dict = {str(case.get('id', '')): case for case in cases}
            logger.info(f"已加载 {len(self.cases_dict)} 个方案到内存")
        except Exception as e:
            logger.error(f"加载方案数据失败: {e}")
            self.cases_dict = {}
    
    def retrieve_similar_cases(
        self,
        query: str,
        top_k: int = 3,
        similarity_threshold: float = 0.6,
        domain_filter: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        检索相似方案
        
        Args:
            query: 用户查询文本
            top_k: 返回Top-K个结果
            similarity_threshold: 相似度阈值（0-1之间）
            domain_filter: 领域过滤（可选），如"工业电子"、"消费电子"等
            
        Returns:
            相似方案列表，每个元素包含：
            - case_id: 方案ID
            - similarity: 相似度分数
            - project_name: 项目名称
            - project_domain: 项目领域
            - project_number: 项目编号
            - module_details: 模块详细信息
            - raw_data: 原始数据
        """
        try:
            # 1. 向量相似度搜索（多检索一些，用于后续过滤）
            docs_with_scores = self.vectorstore.similarity_search_with_score(
                query, k=top_k * 3  # 多检索一些，用于过滤
            )
            
            # 2. 过滤和格式化结果
            results = []
            for doc, score in docs_with_scores:
                # FAISS返回的是L2距离，转换为相似度（使用1/(1+distance)或1-distance）
                # 这里使用简单的转换：similarity = max(0, 1 - distance)
                similarity = max(0.0, 1.0 - score)
                
                if similarity < similarity_threshold:
                    continue
                
                metadata = doc.metadata
                case_id = str(metadata.get('case_id', ''))
                raw_case = self.cases_dict.get(case_id, {})
                
                if not raw_case:
                    continue
                
                # 领域过滤
                if domain_filter:
                    domain = metadata.get('domain', '')
                    if domain_filter not in domain:
                        continue
                
                # 构建结果
                result = {
                    'case_id': case_id,
                    'similarity': float(similarity),
                    'project_name': metadata.get('project_name', ''),
                    'project_domain': metadata.get('domain', ''),
                    'project_number': metadata.get('project_number', ''),
                    'raw_data': raw_case,
                    'module_details': extract_module_details(raw_case)
                }
                results.append(result)
                
                if len(results) >= top_k:
                    break
            
            # 如果结果不足，降低阈值重试
            if len(results) < top_k and similarity_threshold > 0.4:
                logger.info(f"相似方案不足{top_k}个，降低阈值重试...")
                return self.retrieve_similar_cases(
                    query, top_k, similarity_threshold - 0.1, domain_filter
                )
            
            return results
            
        except Exception as e:
            logger.error(f"检索相似方案失败: {e}")
            return []
    
    def format_cases_for_llm(
        self,
        similar_cases: List[Dict[str, Any]],
        max_tokens: int = 1000
    ) -> str:
        """
        将检索结果格式化为LLM可用的文本
        
        Args:
            similar_cases: retrieve_similar_cases() 返回的结果列表
            max_tokens: 最大token数（粗略估算）
            
        Returns:
            格式化后的文本字符串
        """
        if not similar_cases:
            return ""
        
        formatted_parts = []
        current_tokens = 0
        
        # 添加标题
        formatted_parts.append("## 📚 历史参考方案")
        current_tokens += 20
        
        for i, case in enumerate(similar_cases, 1):
            case_text = f"\n### 参考方案 {i}: {case['project_name']}\n"
            case_text += f"- **相似度**: {case['similarity']:.2%}\n"
            
            if case['project_domain']:
                # 提取主要领域
                main_domain = case['project_domain'].split(',')[0].split('(')[0] if case['project_domain'] else ''
                if main_domain:
                    case_text += f"- **应用领域**: {main_domain}\n"
            
            if case['project_number']:
                case_text += f"- **项目编号**: {case['project_number']}\n"
            
            # 添加模块信息
            module_details = case.get('module_details', {})
            if module_details:
                case_text += "\n**关键模块信息**:\n"
                for module_name, module_info in module_details.items():
                    module_text = f"  - **{module_name}**: "
                    parts_list = []
                    
                    if module_info.get('description') and module_info.get('description') != 'NA':
                        parts_list.append(f"描述({module_info['description']})")
                    
                    external_parts = module_info.get('external_parts', [])
                    if external_parts:
                        parts_list.append(f"外部物料({', '.join(external_parts)})")
                    
                    internal_parts = module_info.get('internal_parts', [])
                    if internal_parts:
                        parts_list.append(f"内部物料({', '.join(internal_parts)})")
                    
                    if parts_list:
                        module_text += ", ".join(parts_list) + "\n"
                        case_text += module_text
            
            # 粗略估算token数（中文字符*1.5，英文单词*1）
            estimated_tokens = len(case_text) * 1.5
            if current_tokens + estimated_tokens > max_tokens:
                break
            
            formatted_parts.append(case_text)
            current_tokens += estimated_tokens
        
        result_text = "\n".join(formatted_parts)
        
        if not result_text.strip():
            return ""
        
        return result_text + "\n\n---\n"


def create_rag_retriever(
    embedding_model,
    data_path: str,
    index_path: str = './expert_case_index',
    rebuild_index: bool = False
) -> Optional[RAGRetriever]:
    """
    创建RAG检索器
    
    Args:
        embedding_model: 向量化模型（HuggingFaceEmbeddings实例）
        data_path: JSON数据文件路径
        index_path: FAISS索引保存路径
        rebuild_index: 是否重建索引
        
    Returns:
        RAGRetriever实例，如果失败返回None
    """
    try:
        # 1. 检查数据文件是否存在
        if not os.path.exists(data_path):
            logger.error(f"数据文件不存在: {data_path}")
            return None
        
        # 2. 检查索引是否存在
        index_exists = os.path.exists(index_path) and os.path.exists(
            os.path.join(index_path, 'index.faiss')
        )
        
        if index_exists and not rebuild_index:
            logger.info(f"加载已有索引: {index_path}")
            try:
                vectorstore = FAISS.load_local(index_path, embedding_model)
                logger.info("索引加载成功")
                return RAGRetriever(vectorstore, data_path)
            except Exception as e:
                logger.warning(f"加载索引失败: {e}，将重新构建")
                rebuild_index = True
        
        # 3. 读取JSON数据
        logger.info(f"读取数据文件: {data_path}")
        with open(data_path, 'r', encoding='utf-8') as f:
            cases = json.load(f)
        
        if not cases:
            logger.error("数据文件为空")
            return None
        
        logger.info(f"共读取 {len(cases)} 个方案")
        
        # 4. 构建文档列表
        documents = []
        metadata_list = []
        
        for case in cases:
            # 构建可检索文本
            text = build_searchable_text(case)
            
            if not text.strip():
                continue
            
            # 创建Document对象
            case_id = str(case.get('id', ''))
            if not case_id:
                logger.warning(f"方案缺少ID字段，跳过: {case.get('crmPjProjectIdName', 'Unknown')}")
                continue
            
            doc = Document(
                page_content=text,
                metadata={
                    'case_id': case_id,
                    'project_id': str(case.get('crmPjProjectId', '')),
                    'project_name': case.get('crmPjProjectIdName', ''),
                    'project_number': case.get('crmPjProjectNumber', ''),
                    'domain': case.get('otherProjectSegmentsName', ''),
                    'customer_product': case.get('customerProductName', '')
                }
            )
            documents.append(doc)
        
        if not documents:
            logger.error("没有有效的文档可以索引")
            return None
        
        logger.info(f"构建了 {len(documents)} 个可检索文档")
        
        # 5. 构建FAISS索引
        logger.info("正在构建向量索引...")
        vectorstore = FAISS.from_documents(documents, embedding_model)
        
        # 6. 保存索引
        os.makedirs(index_path, exist_ok=True)
        vectorstore.save_local(index_path)
        logger.info(f"索引已保存到: {index_path}")
        
        return RAGRetriever(vectorstore, data_path)
        
    except Exception as e:
        logger.error(f"创建RAG检索器失败: {e}", exc_info=True)
        return None


# 测试代码
if __name__ == "__main__":
    from langchain_community.embeddings import HuggingFaceEmbeddings
    
    # 初始化向量化模型
    embedding_model = HuggingFaceEmbeddings(
        model_name='../paraphrase-multilingual-MiniLM-L12-v2',
        cache_folder='/data/alg/fae/paraphrase-multilingual-MiniLM-L12-v2',
        model_kwargs={'local_files_only': True}
    )
    
    # 创建RAG检索器
    retriever = create_rag_retriever(
        embedding_model=embedding_model,
        data_path='./all_data_20.json',
        index_path='./expert_case_index',
        rebuild_index=True  # 首次运行设为True
    )
    
    if retriever:
        # 测试检索
        query = "需要设计一个医疗设备，使用STM32主控，12V输入3.3V输出"
        similar_cases = retriever.retrieve_similar_cases(
            query=query,
            top_k=3,
            similarity_threshold=0.6
        )
        
        print(f"\n检索到 {len(similar_cases)} 个相似方案:")
        for case in similar_cases:
            print(f"\n方案ID: {case['case_id']}")
            print(f"项目名称: {case['project_name']}")
            print(f"相似度: {case['similarity']:.2%}")
            print(f"模块数量: {len(case['module_details'])}")
        
        # 格式化输出
        formatted = retriever.format_cases_for_llm(similar_cases, max_tokens=800)
        print("\n格式化后的文本:")
        print(formatted)
