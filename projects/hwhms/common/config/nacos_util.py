import logging

import nacos
from nacos import NacosClient

from projects.hwhms.common.config import global_config

logger = logging.getLogger(__name__)
_client: NacosClient = None



def init_nacos():
    global _client
    # 创建一个连接对象
    _client = nacos.NacosClient(global_config.nacos_server_address, namespace=global_config.nacos_env,
                                username=global_config.nacos_username,
                                password=global_config.nacos_pwd)
    logger.info(f'nacos_client = {_client.get_server()},nacos_env = {global_config.nacos_env} ')


def get_nacos_client():
    return _client
