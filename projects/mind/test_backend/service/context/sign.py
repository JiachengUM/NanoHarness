import hashlib
import hmac
import base64
import json
import re
import urllib.parse


def parse_auth_config(file_path: str) -> dict:
    """从鉴权文件解析配置"""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    config = {
        'common_params': {},
        'auth': {}
    }

    # 解析公参 JSON
    common_params_match = re.search(r'"ai_car_common_params":\s*({[^}]+})', content, re.DOTALL)
    if common_params_match:
        try:
            config['common_params'] = json.loads(common_params_match.group(1))
        except json.JSONDecodeError:
            # 尝试修复可能的 JSON 格式问题
            json_str = common_params_match.group(1)
            json_str = re.sub(r'(\w+):', r'"\1":', json_str)
            json_str = json_str.replace("'", '"')
            config['common_params'] = json.loads(json_str)

    # 解析鉴权信息
    ak_match = re.search(r'AK="([^"]+)"', content)
    sk_match = re.search(r'SK="([^"]+)"', content)
    env_match = re.search(r'env="([^"]+)"', content)
    channel_match = re.search(r'channel="([^"]+)"', content)
    app_id_match = re.search(r'app_id=(\d+)', content)
    channel_app_id_match = re.search(r'channel_app_id=(\d+)', content)

    if ak_match:
        config['auth']['ak'] = ak_match.group(1)
    if sk_match:
        config['auth']['sk'] = sk_match.group(1)
    if env_match:
        config['auth']['env'] = env_match.group(1)
    if channel_match:
        config['auth']['channel'] = channel_match.group(1)
    if app_id_match:
        config['auth']['app_id'] = int(app_id_match.group(1))
    if channel_app_id_match:
        config['auth']['channel_app_id'] = int(channel_app_id_match.group(1))

    return config


def gen_sign(method: str, querystr: str, sk: str, body: str = None) -> str:
    """
    生成签名
    签名算法: HMAC-SHA256
    """
    # 对 query string 进行 URL 编码
    querystr = urllib.parse.quote(querystr, safe=':/&=')

    # 按 key 排序
    a = querystr.split("&")
    a.sort()
    sortedquerystr = "&".join(a)

    # 构造签名字符串
    strtosign = method + "\n" + sortedquerystr + "\n"

    if body is not None and len(body) > 0:
        m = hashlib.md5()
        m.update(body.encode("utf8"))
        strtosign += m.hexdigest() + "\n"

    # HMAC-SHA256 计算
    h = hmac.new(sk.encode("utf8"), strtosign.encode("utf8"), hashlib.sha256).digest()
    return base64.b64encode(h).decode()
