"""
RAG (Retrieval-Augmented Generation) 相关功能
用于判断查询是否属于传统垂域
"""
import json
import logging
import time
from typing import Optional

import aiohttp
from pydantic import BaseModel, Field
from volcengine.Credentials import Credentials
from volcengine.auth.SignerV4 import SignerV4
from volcengine.base.Request import Request

from projects.hwhms.common.config.config import AppConfig

logger = logging.getLogger(__name__)


# RAG判断传统垂域的阈值（基于分析结果优化）
RAG_TRADITIONAL_THRESHOLD = 0.95  # 相似度阈值，超过此值认为是传统垂域


class RagSearchResult(BaseModel):
    """RAG搜索结果"""
    query: str = Field(..., description="查询内容")
    max_similarity: float = Field(..., description="最大相似度分数")
    is_traditional: bool = Field(..., description="是否属于传统垂域")

class RagSearchMustPassResult(BaseModel):
    """RAG搜索结果"""
    query: str = Field(..., description="查询内容")
    max_similarity: float = Field(..., description="最大相似度分数")
    ground_truth: Optional[str] = Field(None, description="期望落域")


def prepare_rag_request(method: str, path: str, params=None, data=None, doseq=0):
    """准备火山引擎API请求"""
    if params:
        for key in params:
            if (
                isinstance(params[key], int)
                or isinstance(params[key], float)
                or isinstance(params[key], bool)
            ):
                params[key] = str(params[key])
            elif isinstance(params[key], list):
                if not doseq:
                    params[key] = ",".join(params[key])

    r = Request()
    r.set_shema("http")
    r.set_method(method)
    r.set_connection_timeout(30)
    r.set_socket_timeout(30)

    mheaders = {
        "Accept": "application/json",
        "Content-Type": "application/json; charset=utf-8",
        "Host": AppConfig.RAG_KNOWLEDGE_BASE_DOMAIN,
        "V-Account-Id": AppConfig.RAG_ACCOUNT_ID,
    }
    r.set_headers(mheaders)

    if params:
        r.set_query(params)
    r.set_host(AppConfig.RAG_KNOWLEDGE_BASE_DOMAIN)
    r.set_path(path)

    if data is not None:
        r.set_body(json.dumps(data))

    # 生成签名
    credentials = Credentials(AppConfig.RAG_AK, AppConfig.RAG_SK, "air", "cn-north-1")
    SignerV4.sign(r, credentials)
    return r


async def rag_search_traditional(query: str) -> RagSearchResult:
    """使用RAG搜索判断是否属于传统垂域"""
    start_time = time.time()
    logger.info(f"🚀 rag_search_traditional 开始执行")
    request_params = {
        "project": AppConfig.RAG_PROJECT_NAME,
        "name": AppConfig.RAG_COLLECTION_NAME,
        "query": query,
        # 降低返回条数以减少响应体大小和服务端负载
        "limit": 3,
        "pre_processing": {"need_instruction": False, "return_token_usage": False, "messages": []},
        "dense_weight": 1,
        "post_processing": {"get_attachment_link": False, "rerank_only_chunk": False, "rerank_switch": False},
        "query_param": {
            "doc_filter ":{
                    "op": "and", 
                    "conds": [
                    {
                        "op": "must",
                        "field": "doc_id",
                        "conds": [
                            "_sys_auto_gen_doc_id-11490495800983731394"
                        ]
                    }
                ]
            }
        }
    }

    info_req = prepare_rag_request(method="POST", path="/api/knowledge/collection/search_knowledge", data=request_params)
    logger.info(f"✅ rag_traditional: prepare_request 完成，耗时: {time.time() - start_time:.3f}秒")

    # 使用局部会话，避免连接泄漏
    session_start = time.time()
    try:
        async with aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(limit=100, limit_per_host=50, ssl=False)  # 增加连接池
        ) as session:
            logger.info(f"✅ rag_traditional: ClientSession 创建完成，耗时: {time.time() - session_start:.3f}秒")
            request_start = time.time()
            async with session.post(
                url=f"http://{AppConfig.RAG_KNOWLEDGE_BASE_DOMAIN}{info_req.path}",
                headers=info_req.headers,
                data=info_req.body,
                timeout=aiohttp.ClientTimeout(total=15, connect=5)  # 增加超时时间
            ) as response:
                logger.info(f"✅ rag_traditional: HTTP请求完成，耗时: {time.time() - request_start:.3f}秒")
                if response.status == 200:
                    raw_response = await response.json()
                    # 提取最大相似度
                    max_similarity = 0.0
                    if raw_response and 'data' in raw_response and 'result_list' in raw_response['data']:
                        result_list = raw_response['data']['result_list']
                        logger.info(f"rag_traditional: result_list: {result_list}")
                        if result_list:
                            similarities = [float(result['score']) for result in result_list if 'score' in result]
                            max_similarity = max(similarities) if similarities else 0.0
                    
                    # 判断是否属于传统垂域
                    is_traditional = max_similarity >= RAG_TRADITIONAL_THRESHOLD
                    logger.info(f"✅ rag_search_traditional 完成，耗时: {time.time() - start_time:.2f}秒")
                    return RagSearchResult(
                        query=query, 
                        max_similarity=max_similarity, 
                        is_traditional=is_traditional
                    )
                else:
                    return RagSearchResult(query=query, max_similarity=0.0, is_traditional=False)
    except Exception:
        # 如果RAG搜索失败，返回非传统垂域结果
        return RagSearchResult(query=query, max_similarity=0.0, is_traditional=False)



async def rag_search_must_pass(query: str) -> RagSearchMustPassResult:
    """使用RAG搜索判断是否属于传统垂域"""
    start_time = time.time()
    request_params = {
        "project": AppConfig.RAG_PROJECT_NAME,
        "name": AppConfig.RAG_COLLECTION_NAME_MUST_PASS,
        "query": query,
        # 降低返回条数以减少响应体大小和服务端负载
        "limit": 3,
        "pre_processing": {"need_instruction": False, "return_token_usage": False, "messages": []},
        "dense_weight": 1,
        "post_processing": {"get_attachment_link": False, "rerank_only_chunk": False, "rerank_switch": False}
    }

    info_req = prepare_rag_request(method="POST", path="/api/knowledge/collection/search_knowledge", data=request_params)

    # 使用局部会话，避免连接泄漏
    try:
        async with aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(limit=100, limit_per_host=50, ssl=False)  # 增加连接池
        ) as session:
            async with session.post(
                url=f"http://{AppConfig.RAG_KNOWLEDGE_BASE_DOMAIN}{info_req.path}",
                headers=info_req.headers,
                data=info_req.body,
                timeout=aiohttp.ClientTimeout(total=15, connect=5)  # 增加超时时间
            ) as response:
                if response.status == 200:
                    raw_response = await response.json()
                    # 提取最大相似度
                    max_similarity = 0.0
                    if raw_response and 'data' in raw_response and 'result_list' in raw_response['data']:
                        result_list = raw_response['data']['result_list']
                        logger.info(f"rag_search_must_pass: result_list: {result_list}")
                        if result_list:
                            ## 提取最大相似度的记录
                            max_similarity_record = max(result_list, key=lambda x: x['score'])
                            max_similarity = max_similarity_record['score']
                            table_chunk_fields = max_similarity_record['table_chunk_fields']
                            for field in table_chunk_fields:
                                if field['field_name'] == '模型输出':
                                    ground_truth = field['field_value']
                                    break
                    
                    logger.info(f"rag_search_must_pass 完成，耗时: {time.time() - start_time:.2f}秒")
                    return RagSearchMustPassResult(
                        query=query, 
                        max_similarity=max_similarity, 
                        ground_truth=ground_truth
                    )
                else:
                    return RagSearchMustPassResult(query=query, max_similarity=0.0, ground_truth=None)
    except Exception as e:
        print(f"rag_search_must_pass error: {e}")

        # 如果RAG搜索失败，返回非传统垂域结果
        return RagSearchMustPassResult(query=query, max_similarity=0.0, ground_truth=None)


