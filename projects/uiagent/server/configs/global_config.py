import logging
import os

logger = logging.getLogger(__name__)

agent_env = os.getenv('AGENT_ENV', "extour-dev")
nacos_env = "llm_dev_volc"
nacos_server_address = "127.0.0.1:8848"
nacos_username = "nacos"
nacos_pwd = "nacos"


# 环境切换
def init_env():
    global nacos_env
    global nacos_server_address
    global nacos_username
    global nacos_pwd

    if agent_env == 'local':
        nacos_env = "llm_dev_volc"
        nacos_server_address = "127.0.0.1:8848"
        nacos_username = "nacos"
        nacos_pwd = "nacos"
    elif agent_env == 'extour-dev':
        nacos_env = "llm_dev_volc_nanoai"
        nacos_server_address = "118.31.22.57:8848"
        nacos_username = "nacos"
        nacos_pwd = ""
    elif agent_env == 'dev':
        nacos_env = "csvw-abc"
        nacos_server_address = "10.20.10.30:8848"
        nacos_username = "nacos"
        nacos_pwd = "+OZt4lN_"
    elif agent_env == 'prd':
        nacos_env = "csvw-abc"
        nacos_server_address = "10.20.10.30:8848"
        nacos_username = "nacos"
        nacos_pwd = "+OZt4lN_"


init_env()
