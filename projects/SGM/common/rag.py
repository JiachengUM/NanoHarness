"""
RAG (Retrieval-Augmented Generation) 相关功能
用于判断查询是否属于多意图
"""
from ast import Str
from enum import StrEnum
import json
import aiohttp
import asyncio
import logging
from typing import Optional
from pydantic import BaseModel, Field
from volcengine.auth.SignerV4 import SignerV4
from volcengine.base.Request import Request
from volcengine.Credentials import Credentials

logger = logging.getLogger(__name__)

# 全局共享的 aiohttp ClientSession（单例模式，支持连接池复用）
_rag_session: Optional[aiohttp.ClientSession] = None

def get_rag_session() -> aiohttp.ClientSession:
    """获取全局共享的 RAG 检索会话（单例模式，支持连接池复用）"""
    global _rag_session
    if _rag_session is None or _rag_session.closed:
        _rag_session = aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(
                limit=100,  # 总连接数限制
                limit_per_host=50,  # 每个主机的连接数限制
                ssl=False
            ),
            timeout=aiohttp.ClientTimeout(total=30, connect=10)  # 增加超时时间到30秒，避免批量测试时超时
        )
    return _rag_session

async def close_rag_session():
    """关闭全局 RAG 会话（用于程序退出时清理资源）"""
    global _rag_session
    if _rag_session is not None and not _rag_session.closed:
        await _rag_session.close()
        _rag_session = None

# ===================== RAG配置 =====================
# 火山引擎配置
RAG_AK = "REDACTED"
RAG_SK = "TkdFMVkyVm1OREk0WmpkbE5HWmhZbUV6WW1NelltWTVNRFptWTJGa016Yw=="
RAG_KNOWLEDGE_BASE_DOMAIN = "api-knowledgebase.mlp.cn-beijing.volces.com"
RAG_ACCOUNT_ID = "2106693029"
RAG_PROJECT_NAME = "default"
RAG_COLLECTION_NAME = "multi_intent"

# RAG判断多意图的阈值
RAG_MULTI_INTENT_THRESHOLD = 0.85  # 相似度阈值，超过此值认为是多意图


class RagSearchResult(BaseModel):
    """RAG搜索结果"""
    query: str = Field(..., description="查询内容")
    max_similarity: float = Field(..., description="最大相似度分数")
    is_multi_intent: bool = Field(..., description="是否属于多意图")


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
        "Host": RAG_KNOWLEDGE_BASE_DOMAIN,
        "V-Account-Id": RAG_ACCOUNT_ID,
    }
    r.set_headers(mheaders)

    if params:
        r.set_query(params)
    r.set_host(RAG_KNOWLEDGE_BASE_DOMAIN)
    r.set_path(path)

    if data is not None:
        r.set_body(json.dumps(data))

    # 生成签名
    credentials = Credentials(RAG_AK, RAG_SK, "air", "cn-north-1")
    SignerV4.sign(r, credentials)
    return r


async def rag_search_multi_intent(query: str) -> RagSearchResult:
    """使用RAG搜索判断是否属于多意图"""
    request_params = {
        "project": RAG_PROJECT_NAME,
        "name": RAG_COLLECTION_NAME,
        "query": query,
        # 降低返回条数以减少响应体大小和服务端负载
        "limit": 3,
        "pre_processing": {"need_instruction": False, "return_token_usage": False, "messages": []},
        "dense_weight": 1,
        "post_processing": {"get_attachment_link": False, "rerank_only_chunk": False, "rerank_switch": False}
    }

    info_req = prepare_rag_request(method="POST", path="/api/knowledge/collection/search_knowledge", data=request_params)

    # 使用全局共享的会话，支持连接池复用
    try:
        session = get_rag_session()
        async with session.post(
            url=f"http://{RAG_KNOWLEDGE_BASE_DOMAIN}{info_req.path}",
            headers=info_req.headers,
            data=info_req.body,
        ) as response:
                if response.status == 200:
                    raw_response = await response.json()
                    # 提取最大相似度
                    max_similarity = 0.0
                    if raw_response and 'data' in raw_response and 'result_list' in raw_response['data']:
                        result_list = raw_response['data']['result_list']
                        if result_list:
                            similarities = [float(result['score']) for result in result_list if 'score' in result]
                            max_similarity = max(similarities) if similarities else 0.0
                            logger.debug(f"RAG检索成功: query={query[:50]}, 结果数={len(result_list)}, 最大相似度={max_similarity:.4f}")
                        else:
                            logger.debug(f"RAG检索返回空结果列表: query={query[:50]}")
                    else:
                        logger.debug(f"RAG检索响应格式异常: query={query[:50]}, 响应keys={list(raw_response.keys()) if raw_response else 'None'}")
                    
                    # 判断是否属于多意图
                    is_multi_intent = max_similarity >= RAG_MULTI_INTENT_THRESHOLD
                    
                    return RagSearchResult(
                        query=query, 
                        max_similarity=max_similarity, 
                        is_multi_intent=is_multi_intent
                    )
                else:
                    logger.warning(f"RAG检索返回非200状态码: {response.status}, query: {query[:50]}")
                    return RagSearchResult(query=query, max_similarity=0.0, is_multi_intent=False)
    except asyncio.TimeoutError:
        logger.warning(f"RAG检索超时, query: {query[:50]}")
        return RagSearchResult(query=query, max_similarity=0.0, is_multi_intent=False)
    except aiohttp.ClientError as e:
        logger.warning(f"RAG检索网络错误: {e}, query: {query[:50]}")
        return RagSearchResult(query=query, max_similarity=0.0, is_multi_intent=False)
    except Exception as e:
        logger.warning(f"RAG检索异常: {type(e).__name__}: {e}, query: {query[:50]}")
        return RagSearchResult(query=query, max_similarity=0.0, is_multi_intent=False)