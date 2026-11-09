from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv
import json
import httpx
from pydantic import BaseModel, Field

# TODO: 下面对于volcengine的依赖完全没有必要，可以重构掉。只是有些麻烦
from volcengine.base.Request import Request
from volcengine.Credentials import Credentials
from volcengine.auth.SignerV4 import SignerV4

__all__ = [
    "request",
    # "ApiResponseModel",  # 还不成熟
]

# TODO: 增加client概念
# TODO: 去掉env文件，构造缺省client

# 加载 .env 文件
_env_path = Path(__file__).parent / ".env"
if _env_path.exists():
    load_dotenv(_env_path)

# 从环境变量读取配置，如果没有则使用默认值
AK = os.environ.get("AK")
SK = os.environ.get("SK")

DOMAIN = os.environ.get("DOMAIN", "api-knowledgebase.mlp.cn-beijing.volces.com")
SERVICE = os.environ.get("SERVICE", "air")
REGION = os.environ.get("REGION", "cn-north-1")
SCHEMA = os.environ.get("SCHEMA", "http")


# TODO: 这个Request有点蠢。改写成BaseModel。
# TODO: 这个Credentials也很蠢。改写成BaseModel。
# TODO: SignerV4.sign也很蠢。重写。它就是在构造request。这些都需要一起改，有点麻烦。
def _prepare_request(method: str, path: str, data: dict | None = None) -> Request:
    """构建并签名火山引擎 API 请求"""
    r = Request()
    r.set_shema(SCHEMA)
    r.set_method(method)
    r.set_host(DOMAIN)
    r.set_path(path)

    if data is not None:
        r.set_body(json.dumps(data, ensure_ascii=False))

    credentials = Credentials(AK, SK, SERVICE, REGION)
    SignerV4.sign(r, credentials)
    return r

class ApiResponseModel(BaseModel):
    """
    对于http API的通用响应模型。
    目前还没有任何关于火山引擎API的定制化和优化，是通用的，但过于简单粗糙。暂时只用于mem API。
    TODO: 有更多通用需求后，进一步强化进入底层API。
    """

    # model_config = {"frozen": True}  # 暂时还不能frozen，因为data可能被外部修改

    success: bool = Field(..., description="请求是否成功")
    status_code: int = Field(..., description="HTTP 状态码")
    data: dict | BaseModel = Field(..., description="响应数据")
    
    @classmethod
    def from_response(cls, response: httpx.Response) -> ApiResponseModel:
        """从 httpx.Response 创建 ApiResponse"""
        data = response.json()
        success = 200 <= response.status_code < 300
                
        return cls(
            success=success,
            status_code=response.status_code,
            data=data
        )


def request(
    method: str,
    api: str,
    payload: dict,
    /,
    *,
    params: dict | None = None,
    output_type: type[BaseModel | dict] = dict,
) -> ApiResponseModel:
    """
    发送HTTP 请求并返回 ApiResponse。
    如果 output_type 为 BaseModel 类型，则将 ApiResponse的data 字段解析为该类型。
    """
    req = _prepare_request(method, api, payload)

    # TODO: 处理异常

    response = httpx.request(
        method=req.method,
        url=f"{req.schema}://{req.host}{req.path}",
        headers=req.headers,
        content=req.body,
        params=params,
    )
    
    rsp = ApiResponseModel.from_response(response)

    assert isinstance(rsp.data, dict)

    if rsp.success:
        # 某些 API 返回的数据在 "Result" 字段中，某些直接返回数据
        # 如果存在 "Result" 字段，则使用它；否则使用整个 data
        if "Result" in rsp.data:
            rsp.data = rsp.data["Result"]
        # 如果不存在 "Result"，保持 rsp.data 不变（已经是完整响应）
        return rsp
    else:
        # TODO: 这里统一定义异常类型

        # 下面的写法似乎只对于collection部分的API有效。
        # raise Exception(f"{rsp.data["ResponseMetadata"]['Error']}")

        raise Exception(f"{rsp.data}")