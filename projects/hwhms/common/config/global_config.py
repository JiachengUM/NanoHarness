import logging
import os

logger = logging.getLogger(__name__)

agent_env = os.environ.get("AGENT_ENV", "test")
nacos_env = os.environ.get("NACOS_ENV", "llm_dev_volc_huawei")
nacos_server_address = os.environ.get("NACOS_SERVER_ADDRESS", "118.31.22.57:8848")
nacos_username = os.environ.get("NACOS_USERNAME", "nacos")
nacos_pwd = os.environ.get("NACOS_PWD", "")


# 环境切换
def init_env():
    global nacos_env
    global nacos_server_address
    global nacos_username
    global nacos_pwd

    if agent_env == 'test':
        nacos_env = nacos_env
        nacos_server_address = nacos_server_address
        nacos_username = nacos_username
        nacos_pwd = nacos_pwd

    elif agent_env == 'dev':
        nacos_env = nacos_env
        nacos_server_address = nacos_server_address
        nacos_username = nacos_username
        nacos_pwd = nacos_pwd
    


init_env()
