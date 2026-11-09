
import base64
import hashlib
import hmac
import logging
import random
import time
import uuid
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class VolcengineUtils:

    @staticmethod
    def prepare_querystr(
           
    ) -> str:
        query_params = {
            "X-Use-PPE": "1",
            "X-Tt-Env": "ppe_vehicle_model_huawei_test",
            "vehicle_id":str(uuid.uuid4()),
            "_nonce":random.randint(1000, 9999),
            "_timestamp":int(time.time()),
            "channel":"huaweihms",
            "app_id":"99490"
        }
        querystr = "&".join([f"{k}={v}" for k, v in sorted(query_params.items())])
        return querystr

    @staticmethod
    def prepare_headers_http(x_signature: str) -> Dict[str, str]:
        headers = {
            "X-Use-PPE": "1",
            "X-Tt-Env": "ppe_vehicle_model_huawei_test",
            "vehicle_id":str(uuid.uuid4()),
            "channel":"huaweihms",
            "app_id":"99490",
            "Content-Type": "application/json",
            "X-Signature": x_signature,
        }
        return headers

    @staticmethod
    def generate_signature(method: str, querystr: str, body: Optional[str], sk: str) -> str:
        """生成请求签名"""
        try:
            # 对查询参数按字典序排序
            a = querystr.split("&")
            a.sort()
            sortedquerystr = "&".join(a)

            # 构建待签名字符串
            strtosign = method + "\n" + sortedquerystr + "\n"
            if body is not None and len(body) > 0:
                m = hashlib.md5()
                m.update(body.encode("utf8"))
                strtosign += m.hexdigest() + "\n"

            # 计算HMAC-SHA256签名
            h = hmac.new(sk.encode("utf8"), strtosign.encode("utf8"), hashlib.sha256).digest()
            signature = base64.b64encode(h).decode()
            logger.debug("Generated signature successfully")
            return signature
        except Exception as e:
            error_msg = f"Signature generation failed: {e}"
            logger.error(error_msg, exc_info=True)
            raise RuntimeError(error_msg)
