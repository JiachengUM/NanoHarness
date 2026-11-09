#!/usr/bin/env python3
import csv
import json
import aiohttp
import time
from pathlib import Path
from typing import List
from volcengine.auth.SignerV4 import SignerV4
from volcengine.base.Request import Request
from volcengine.Credentials import Credentials
from pydantic import BaseModel, Field
from nanoai.utils.async_utils import amap
from projects.hwhms.common.config.config import AppConfig




class SearchResult(BaseModel):
    """查询搜索结果"""
    query: str = Field(..., description="查询内容")
    max_similarity: float = Field(..., description="最大相似度分数")


def prepare_request(method: str, path: str, params=None, data=None, doseq=0):
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


async def single_search(session: aiohttp.ClientSession, query: str) -> SearchResult:
    """异步搜索单个查询"""
    request_params = {
        "project": AppConfig.RAG_PROJECT_NAME,
        "name": AppConfig.RAG_COLLECTION_NAME,
        "query": query,
        "limit": 3,
        "pre_processing": {"need_instruction": False, "return_token_usage": False, "messages": []},
        "dense_weight": 1,
        "post_processing": {"get_attachment_link": False, "rerank_only_chunk": False, "rerank_switch": False}
    }

    info_req = prepare_request(method="POST", path="/api/knowledge/collection/search_knowledge", data=request_params)

    async with session.post(
        url=f"http://{AppConfig.RAG_KNOWLEDGE_BASE_DOMAIN}{info_req.path}",
        headers=info_req.headers,
        data=info_req.body,
        timeout=aiohttp.ClientTimeout(total=30)
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
            
            return SearchResult(query=query, max_similarity=max_similarity)
        else:
            return SearchResult(query=query, max_similarity=0.0)


def read_queries(csv_path: Path) -> List[str]:
    """读取CSV第一列为查询内容"""
    queries = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader)  # 跳过标题行
        for row in reader:
            if row and row[0].strip():
                queries.append(row[0].strip())
    return queries


async def batch_search(input_file: str, output_file: str = None, max_concurrent: int = 10):
    """批量搜索并保存到CSV"""
    here = Path(__file__).resolve().parent
    input_csv_path = here / input_file
    
    if output_file is None:
        output_file = f"{input_file.replace('.csv', '')}_results.csv"
    output_csv_path = here / output_file

    # 读取查询
    queries = read_queries(input_csv_path)
    print(f"读取 {len(queries)} 个查询")

    # 记录开始时间
    start_time = time.time()

    # 使用 nanoai 的 amap 进行并发搜索
    async with aiohttp.ClientSession() as session:
        # 创建带 session 的搜索函数
        async def search_with_session(query: str) -> SearchResult:
            return await single_search(session, query)
        
        # 使用 amap 并发处理
        results, stats = await amap(
            search_with_session, 
            queries, 
            max_concurrent=max_concurrent,
            progress=True  # 显示进度条
        )
    
    # 记录结束时间
    end_time = time.time()
    total_time = end_time - start_time
    
    # 过滤掉异常结果
    valid_results = [r for r in results if not isinstance(r, Exception)]
    
    # 保存结果
    save_results(valid_results, output_csv_path)
    
    # 统计信息
    avg_time_per_query = total_time / len(queries) if queries else 0
    
    print(f"结果已保存到: {output_csv_path}")
    print(f"成功处理: {len(valid_results)}/{len(queries)} 个查询")
    print(f"总耗时: {total_time:.2f} 秒")
    print(f"平均每条耗时: {avg_time_per_query:.3f} 秒")
    
    return valid_results


def save_results(results: List[SearchResult], output_path: Path):
    """保存结果到CSV文件"""
    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["query", "max_similarity"])
        for result in results:
            writer.writerow([result.query, f"{result.max_similarity:.6f}"])


def main():
    """主函数"""
    import sys
    import asyncio
    
    if len(sys.argv) > 1:
        input_file = sys.argv[1]
        print(f"处理 {input_file}...")
        asyncio.run(batch_search(input_file))
    else:
        print("处理 positive.csv 和 negative.csv...")
        asyncio.run(batch_search("positive.csv"))
        asyncio.run(batch_search("negative.csv"))


if __name__ == "__main__":
    main()