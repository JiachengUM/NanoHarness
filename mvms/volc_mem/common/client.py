import json
import requests
from volcengine.base.Request import Request
from volcengine.Credentials import Credentials
from volcengine.auth.SignerV4 import SignerV4

from .config import AK, SK, DOMAIN, SERVICE, REGION, SCHEMA


def prepare_request(method: str, path: str, data: dict | None = None) -> Request:
    """
    构建并签名火山引擎 API 请求
    """
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


def internal_request(
    method: str,
    api: str,
    payload: dict,
    params: dict | None = None,
):
    """
    发送已签名的 HTTP 请求
    """
    req = prepare_request(method, api, payload)

    return requests.request(
        method=req.method,
        url=f"{req.schema}://{req.host}{req.path}",
        headers=req.headers,
        data=req.body,
        params=params,
    )