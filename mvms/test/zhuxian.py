'''
功能说明：
    本脚本用于测试火山引擎记忆服务的两个核心接口：
    1. 查询长期记忆列表（query_memory_list）
    2. 新增历史记录（add_memory）

主要功能：
    - MemoryConfig: 配置管理类，支持多channel自动填充认证信息
    - gen_sign: 生成火山引擎API请求签名
    - query_memory_list: 查询记忆列表接口
    - add_memory: 新增历史记录接口

使用场景：
    - 测试记忆服务的写入和查询功能
    - 验证多轮对话的记忆存储
    - 测试不同查询条件的记忆检索
'''
import random
import time
from typing import Dict, Any, Optional
import httpx
import logging
from dataclasses import dataclass
import json

logger = logging.getLogger(__name__)

import hashlib
import hmac
from hashlib import sha256
import base64
import urllib.parse
import string
from datetime import datetime

VOLC_BASE_URL = "https://api-vehicle.volcengine.com"
VOLC_LONG_TERM_MEMORY_LIST_PATH = "/dpfm/v1/history/long-term-memory/memory"
VOLC_ADD_HISTORY_PATH = "/dpfm/v1/history"


# Channel 到认证信息的映射配置
# 格式: channel -> {"ak": ..., "sk": ..., "x_tt_env": ..., "app_id": ...}
CHANNEL_CREDENTIALS: Dict[str, dict[str, str]] = {
    "saic-gm": {
        "ak": "saicgmtt914b5oglg4f9vxz38a01fme4",
        "sk": "yc57qdqqreosnv2wdwzwo2t7nyce8vgp",
        "x_tt_env": "ppe_vehicle_saicgm_ndlb_test",
        "app_id": 99286,
    },
}


@dataclass
class MemoryConfig:
    """
    记忆服务配置类，支持多个配置预设
    """
    # 必填：业务及基础信息（无默认值，必须传入）
    account_id: str
    channel: str
    vehicle_id: str
    vehicle_type: str

    # 可选：可由 channel 自动填充
    app_id: Optional[int] = None
    ak: Optional[str] = None
    sk: Optional[str] = None
    x_tt_env: Optional[str] = None

    # 可选：请求相关
    content_type: str = "application/json"
    x_use_ppe: str = "1"
    chat_id: str = ""

    def __post_init__(self):
        self._auto_fill_config()
        if not self.account_id:
            raise ValueError("account_id is required and cannot be empty")
        if not self.vehicle_id:
            raise ValueError("vehicle_id is required and cannot be empty")
        if not self.vehicle_type:
            raise ValueError("vehicle_type is required and cannot be empty")
        if not self.channel:
            raise ValueError("channel is required and cannot be empty")
        if not self.app_id:
            raise ValueError("app_id is required and cannot be empty")     
        if not self.ak or not self.sk:
            raise ValueError("ak/sk is required and cannot be empty")    
        if not self.x_tt_env:
            raise ValueError("x_tt_env is required and cannot be empty")

    def _auto_fill_config(self):
        if not self.app_id:
            self.app_id = CHANNEL_CREDENTIALS[self.channel]["app_id"]
        if not self.x_tt_env:
            self.x_tt_env = CHANNEL_CREDENTIALS[self.channel]["x_tt_env"]
        if not self.ak and not self.sk:
            if not CHANNEL_CREDENTIALS[self.channel]["ak"] or not CHANNEL_CREDENTIALS[self.channel]["sk"]:
                return 
            self.ak = CHANNEL_CREDENTIALS[self.channel]["ak"]
            self.sk = CHANNEL_CREDENTIALS[self.channel]["sk"]


    def get_headers(self) -> Dict[str, str]:
        """获取请求头（不包含签名）"""
        return {
            "Content-Type": self.content_type,
            "X-Use-PPE": self.x_use_ppe,
            "X-Tt-Env": self.x_tt_env,
            "X-Signature": "to be calculated",
        }


    def generate_required_common_query_params(self) -> Dict[str, Any]:
        """获取必传查询公共查询参数"""
        params = {
            "channel": self.channel,
            "app_id": self.app_id,
            "vehicle_id": self.vehicle_id,
            "vehicle_type": self.vehicle_type,
            "chat_id": self.chat_id if self.chat_id else datetime.now().strftime("%Y%m%d%H%M%S")+''.join(random.choices(string.ascii_letters,k=8)),
            "account_id": self.account_id,
            "_timestamp": int(time.time()),
            "_nonce": random.randint(0, 65535),
        }
        return params

    def update_common_params(self, **kwargs) -> Dict[str, Any]:
        """
        允许在运行时更新公共参数字段（仅限已知必填字段），返回更新后的公共参数。
        未知字段将报错以避免污染必填集合。
        """
        allowed_fields = {
            "channel",
            "app_id",
            "vehicle_id",
            "vehicle_type",
            "chat_id",
            "account_id",
        }
        for key, value in kwargs.items():
            if key not in allowed_fields:
                raise ValueError(f"不支持更新字段: {key}")
            setattr(self, key, value)
        return self.generate_required_common_query_params()

    def extend_query_params(self, **extra_params):
        """更新查询参数"""
        params = self.generate_required_common_query_params()
        params.update(extra_params)
        return params


def gen_sign(method, querystr, sk, body=None):
    """
    :param method: 请求方式
    :param querystr: 请求内容（已经过 urllib.parse.urlencode 编码）
    :param body: 请求参数
    :param sk: sk
    :return: 加密后的数据
    """
    # querystr 已经通过 urllib.parse.urlencode 编码过了，这里只需要排序
    # 注意：不要再次编码，否则会导致签名不匹配
    a = querystr.split("&")
    a.sort()
    sortedquerystr = "&".join(a)
    strtosign = method + "\n" + sortedquerystr + "\n"
    if body is not None and len(body) > 0:
        m = hashlib.md5()
        m.update(body.encode("utf8"))
        strtosign += m.hexdigest() + "\n"
    h = hmac.new(sk.encode("utf8"), strtosign.encode("utf8"), sha256).digest()
    return base64.b64encode(h).decode()



async def query_memory_list(
    query_params: Dict[str, Any],
    config: Optional[MemoryConfig] = None,
):
    """
    字节主线-记忆查询接口

    :param query_params: 查询参数字典
    :param config: 可选的配置对象，如果不提供则使用默认配置
    :return: 响应对象
    """
    try:
        if config is None:  
            logger.error("未找到配置，请提供有效的 config 参数")
            return None

        headers = config.get_headers()
        query_path = urllib.parse.urlencode(query_params)
        sign = gen_sign("GET", query_path, config.sk)
        # 查询记忆接口必须使用 ppe_session_memory_dev 环境
        headers['X-Tt-Env'] = 'ppe_session_memory_dev'
        headers["X-Signature"] = f"{config.ak}:{sign}"

        url = f"{VOLC_BASE_URL}{VOLC_LONG_TERM_MEMORY_LIST_PATH}"

        async with httpx.AsyncClient() as client:
            response = await client.get(f"{url}?{query_path}", headers=headers)
        print(
            f"query_memory_list headers: {headers} \n"
            f"  query_path: {query_path} \n"
            f"  response headers: {response.headers} \n"
            f"  response: {response.json()} \n\n"
        )

        return response
    except Exception as e:
        logger.error(f"query_memory_list error: {e}")
        return None


async def add_memory(
    query_params: Dict[str, Any], 
    body: Dict[str, Any],
    config: MemoryConfig
):
    """
    字节主线-新增历史接口

    :param query_params: 查询参数字典（包含 channel, app_id, vehicle_id, vehicle_type 等通用参数）
    :param body: 请求体字典，包含 chat_id, history (包含 q 和 a), question_id (可选)
    :param config: 可选的配置对象，如果不提供则使用默认配置
    :return: 响应对象
    """
    try:

        headers = config.get_headers()
        query_path = urllib.parse.urlencode(query_params)


        sign = gen_sign("POST", query_path, config.sk, json.dumps(body, ensure_ascii=False))

        headers["X-Signature"] = f"{config.ak}:{sign}"

        url = f"{VOLC_BASE_URL}{VOLC_ADD_HISTORY_PATH}"
        # POST 请求，body 作为 JSON 发送
        data = json.dumps(body, ensure_ascii=False)
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{url}?{query_path}", headers=headers, content=data.encode("utf-8"))
        print(
            f"add_memory headers: {headers} \n"
            f"  query_path: {query_path} \n"
            f"  body: {body} \n"
            f"  response headers: {response.headers} \n"
            f"  response: {response.json()} \n\n"
        )

        return response
    except Exception as e:
        logger.error(f"add_memory error: {e}")
        return None


if __name__ == "__main__":
    import asyncio

    async def main():
        # SGM 配置
        sgm_config = MemoryConfig(
            channel="saic-gm",
            vehicle_id="vehicle_id-123",
            vehicle_type="test_vehicle",
            account_id="xjc002",
        )

        # case1: 新增记忆
        # 多轮对话数据
        messages = [
            {"role": "user", "content": "我想吃川菜馆"},
            {"role": "assistant", "content": "帮您搜到三家：1. 平金中心店，2. 三里屯店，3. 朝阳大悦城店"},
            {"role": "user", "content": "请帮我导航到第三家"},
            {"role": "assistant", "content": "好的，请稍等，正在为您导航..."},
            {"role": "user", "content": "等一下，请帮我查询一下哪一家比较近"},
            {"role": "assistant", "content": "好的，查询结果第一家离您最近，只需20分钟"},
            {"role": "user", "content": "那就去第一家"},
            {"role": "assistant", "content": "正在重新为您导航..."},
            {"role": "user", "content": "顺道去接一下我老婆，她在七宝古镇逛街"},
            {"role": "assistant", "content": "好的，已为您添加途径点七宝古镇，全程2公里"},
            {"role": "user", "content": "帮我记一下，我外婆家在万达广场3号楼"},
            {"role": "assistant", "content": "已帮您记住了，之后您可以直接说导航到外婆家就行啦"},
        ]

        # 将多轮对话转换为 q-a 对并分别发送
        for i in range(0, len(messages) - 1, 2):
            if messages[i]["role"] == "user" and i + 1 < len(messages) and messages[i + 1]["role"] == "assistant":
                add_history_query = sgm_config.generate_required_common_query_params()
                add_history_body = {
                    "chat_id": add_history_query["chat_id"],
                    "history": {
                        "q": messages[i]["content"],
                        "a": messages[i + 1]["content"]
                    },
                    "extra": {
                        "enable_long_term_memory": "true",
                    }   
                }
                add_resp = await add_memory(add_history_query, add_history_body, config=sgm_config)
                if add_resp is not None and add_resp.is_success:
                    print(f"\n[{i//2 + 1}] {sgm_config.channel} 新增历史 response: {add_resp.json()} log: {add_resp.headers.get('X-Tt-Logid')}\n")
                # 避免请求过快
                await asyncio.sleep(0.5)
        
        # case2: 查询记忆（不带 query）
        sgm_query = sgm_config.extend_query_params(
            limit=3,
            offset=0,
        )
        sgm_resp = await query_memory_list(sgm_query, config=sgm_config)
        if sgm_resp is not None and sgm_resp.is_success:
            print(f"\n\n{sgm_config.channel} 查记忆（全部） response", sgm_resp.json(), f"log: {sgm_resp.headers.get('X-Tt-Logid')}\n\n")
        
        # case3: 查询记忆（带 query，作为 URL 参数）
        sgm_query_with_keyword = sgm_config.extend_query_params(
            query="川菜馆",
            limit=1,
            offset=0,
        )
        sgm_resp_filtered = await query_memory_list(sgm_query_with_keyword, config=sgm_config)
        if sgm_resp_filtered is not None and sgm_resp_filtered.is_success:
            print(f"\n\n{sgm_config.channel} 查记忆（query='川菜馆'，URL参数） response", sgm_resp_filtered.json(), f"log: {sgm_resp_filtered.headers.get('X-Tt-Logid')}\n\n")

    asyncio.run(main())
