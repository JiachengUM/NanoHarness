from __future__ import annotations

import hashlib
import hmac
import json
import os
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

from dotenv import load_dotenv
from pydantic import BaseModel, Field

from aicore.utils.volc_client.httpx_client import HttpClient, HttpResponse

__all__ = [
    "ApiResponseModel",
    "VolcApiClient",
]

_env_path = Path(__file__).parent / ".env"
if _env_path.exists():
    load_dotenv(_env_path)

_DEFAULT_AK      = os.environ.get("AK", "")
_DEFAULT_SK      = os.environ.get("SK", "")
_DEFAULT_DOMAIN  = os.environ.get("DOMAIN", "")
_DEFAULT_SERVICE = os.environ.get("SERVICE", "")
_DEFAULT_REGION  = os.environ.get("REGION", "")
_DEFAULT_SCHEMA  = os.environ.get("SCHEMA", "")


class VolcRequest(BaseModel):
    """V4 签名所需的最小请求模型。"""
    url_schema: str = Field(..., description="请求协议，如 http 或 https")
    method: str = Field(default="", description="HTTP 方法，如 GET、POST")
    host: str = Field(default="", description="请求域名，不包含协议与 path")
    path: str = Field(default="", description="请求路径，如 /api/memory/collection/create")
    headers: OrderedDict[str, str] = Field(default_factory=OrderedDict, description="参与签名与最终发送的请求头")
    query: OrderedDict[str, str] = Field(default_factory=OrderedDict, description="请求 query 参数")
    body: str = Field(default="", description="原始请求体字符串")


class VolcCredentials(BaseModel):
    """V4 签名凭证。"""
    ak: str = Field(...,description="Access Key")
    sk: str = Field(...,description="Secret Key")
    service: str = Field(...,description="火山服务名，如 air")
    region: str = Field(...,description="火山地域，如 cn-north-1")
    session_token: str = Field(default="", description="临时凭证的安全令牌")


class _SignerMeta(BaseModel):
    algorithm: str = Field(default="HMAC-SHA256", description="签名算法名")
    credential_scope: str = Field(default="", description="凭证作用域：date/region/service/request")
    signed_headers: str = Field(default="", description="参与签名的 header 名集合，分号分隔")
    date: str = Field(default="", description="签名日期，格式 YYYYMMDD")
    region: str = Field(default="", description="签名地域")
    service: str = Field(default="", description="签名服务名")


class _SignerV4:
    """
    火山 V4 header 签名的最小实现。

    当前只支持本文件需要的场景：
    - 普通 HTTP header 签名
    - 以请求头 `Authorization` + `X-Date` + `X-Content-Sha256` 的形式发送

    整体过程：
    1. 规范化 path/query/headers/body，构造 canonical request
    2. 对 canonical request 做 sha256，拼出 string to sign
    3. 用 sk 按 date -> region -> service -> request 派生 signing key
    4. 计算最终签名，并写回 `Authorization` 请求头
    """

    @staticmethod
    def sign(request: VolcRequest, credentials: VolcCredentials) -> None:
        # 补齐签名必需头，然后把最终签名直接写回 request.headers。
        if not request.path:
            request.path = "/"
        if request.method != "GET" and "Content-Type" not in request.headers:
            request.headers["Content-Type"] = "application/x-www-form-urlencoded; charset=utf-8"

        format_date = _SignerV4.get_current_format_date()
        request.headers["X-Date"] = format_date
        if credentials.session_token:
            request.headers["X-Security-Token"] = credentials.session_token

        meta = _SignerMeta(
            service=credentials.service,
            region=credentials.region,
            date=format_date[:8],
        )
        hashed_canonical_request = _SignerV4.hashed_canonical_request(request, meta)
        meta.credential_scope = "/".join([meta.date, meta.region, meta.service, "request"])

        signing_str = "\n".join(
            [meta.algorithm, format_date, meta.credential_scope, hashed_canonical_request]
        )
        signing_key = _SignerV4.get_signing_secret_key(
            credentials.sk,
            meta.date,
            meta.region,
            meta.service,
        )
        signature = _SignerV4.to_hex(_SignerV4.hmac_sha256(signing_key, signing_str))
        credential = f"{credentials.ak}/{meta.credential_scope}"
        request.headers["Authorization"] = (
            f"{meta.algorithm} Credential={credential}, "
            f"SignedHeaders={meta.signed_headers}, Signature={signature}"
        )

    @staticmethod
    def hashed_canonical_request(request: VolcRequest, meta: _SignerMeta) -> str:
        # canonical request 是 V4 签名的核心输入，body/query/headers 任一变更都会导致签名变化。
        body_hash = _SignerV4.sha256_hex(request.body)
        request.headers["X-Content-Sha256"] = body_hash

        signed_headers: dict[str, str] = {}
        for key, value in request.headers.items():
            if key in {"Content-Type", "Content-Md5", "Host"} or key.startswith("X-"):
                signed_headers[key.lower()] = value

        host = signed_headers.get("host")
        if host and ":" in host:
            hostname, port = host.split(":", 1)
            if port in {"80", "443"}:
                signed_headers["host"] = hostname

        canonical_headers = "".join(
            f"{key}:{signed_headers[key]}\n" for key in sorted(signed_headers.keys())
        )
        meta.signed_headers = ";".join(sorted(signed_headers.keys()))
        canonical_request = "\n".join(
            [
                request.method,
                _SignerV4.norm_uri(request.path),
                _SignerV4.norm_query(request.query),
                canonical_headers,
                meta.signed_headers,
                body_hash,
            ]
        )
        return _SignerV4.sha256_hex(canonical_request)

    @staticmethod
    def get_signing_secret_key(sk: str, date: str, region: str, service: str) -> bytes:
        # 按 V4 规范逐层派生签名 key，避免直接拿原始 SK 参与最终签名。
        kdate = _SignerV4.hmac_sha256(sk.encode("utf-8"), date)
        kregion = _SignerV4.hmac_sha256(kdate, region)
        kservice = _SignerV4.hmac_sha256(kregion, service)
        return _SignerV4.hmac_sha256(kservice, "request")

    @staticmethod
    def get_current_format_date() -> str:
        return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    @staticmethod
    def hmac_sha256(key: bytes, content: str) -> bytes:
        return hmac.new(key, content.encode("utf-8"), hashlib.sha256).digest()

    @staticmethod
    def sha256_hex(content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    @staticmethod
    def to_hex(content: bytes) -> str:
        return "".join(f"{byte:02x}" for byte in content)

    @staticmethod
    def norm_uri(path: str) -> str:
        return quote(path).replace("%2F", "/").replace("+", "%20")

    @staticmethod
    def norm_query(params: OrderedDict[str, str] | dict[str, str]) -> str:
        if not params:
            return ""
        return "&".join(
            f"{quote(str(key), safe='-_.~')}={quote(str(value), safe='-_.~')}"
            for key, value in sorted(params.items())
        ).replace("+", "%20")


class ApiResponseModel(BaseModel):
    """火山引擎 API 通用响应"""
    success: bool = Field(..., description="请求是否成功")
    status_code: int = Field(..., description="HTTP 状态码")
    data: dict | BaseModel = Field(..., description="响应数据")

    @classmethod
    def from_http_response(cls, rsp: HttpResponse) -> "ApiResponseModel":
        assert rsp.json is not None, "响应体不是 JSON"
        data: dict = rsp.json
        success = 200 <= rsp.status < 300
        if not success:
            raise Exception(f"{data}")
        # 某些接口把真正的数据放在 "Result" 字段
        if "Result" in data:
            data = data["Result"]
        return cls(success=success, status_code=rsp.status, data=data)


class VolcApiClient:
    """
    异步火山引擎 API 客户端。

    使用方式：
        async with httpx.AsyncClient(timeout=10.0) as raw:
            client = VolcApiClient(HttpClient(HttpxTransport(raw)))
            rsp = await client.post("/api/memory/session/add", payload)
    """

    def __init__(
        self,
        http_client: HttpClient,
        *,
        ak: str = _DEFAULT_AK,
        sk: str = _DEFAULT_SK,
        domain: str = _DEFAULT_DOMAIN,
        service: str = _DEFAULT_SERVICE,
        region: str = _DEFAULT_REGION,
        schema: str = _DEFAULT_SCHEMA,
    ) -> None:
        self._http = http_client
        self._ak = ak
        self._sk = sk
        self._domain = domain
        self._service = service
        self._region = region
        self._schema = schema

    def _sign(self, method: str, path: str, body: str) -> dict[str, str]:
        """用 V4 签名，返回签名后的 headers dict。"""
        request = VolcRequest(
            url_schema=self._schema,
            method=method,
            host=self._domain,
            path=path,
            headers=OrderedDict(),
            query=OrderedDict(),
            body=body,
        )
        credentials = VolcCredentials(
            ak=self._ak,
            sk=self._sk,
            service=self._service,
            region=self._region,
        )
        _SignerV4.sign(request, credentials)
        return dict(request.headers)

    async def post(self, path: str, payload: dict) -> ApiResponseModel:
        """发一个签名 POST 请求，返回 ApiResponseModel。"""
        body = json.dumps(payload, ensure_ascii=False)
        headers = self._sign("POST", path, body)
        headers.setdefault("Content-Type", "application/json")
        url = f"{self._schema}://{self._domain}{path}"
        rsp = await self._http.post(url, headers=headers, content_data=body)
        return ApiResponseModel.from_http_response(rsp)
