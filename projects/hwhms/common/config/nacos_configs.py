import logging
from typing import Dict

import yaml
from asgiref.sync import sync_to_async

from projects.hwhms.common.config.nacos_util import get_nacos_client, init_nacos

logger = logging.getLogger("nacos")
logger.setLevel(logging.CRITICAL)
_group = "DEFAULT_GROUP"


class NacosConfigs:
    _volc_config: Dict


    @classmethod
    async def init(cls):
        logger.info("init NacosConfigs")
        cls.init_all()

    @classmethod
    def init_all(cls):
        try:
            _client = get_nacos_client()
            if _client is None:
                logger.error("Nacos client is not initialized")
                init_nacos()
                _client = get_nacos_client()

            volc_config_name = "volc_config"
            volc_config = _client.get_config(data_id=volc_config_name, group=_group)
            cls.volc_config_change_callback({"content": volc_config})
            _client.add_config_watcher(data_id=volc_config_name, group=_group,
                                                  cb=cls.volc_config_change_callback)
            
        except EOFError as e:   
            logger.error(f"EOFError: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to initialize api_key_config (data_id: 'api_key_config', group: '{_group}'): {str(e)} | Error type: {type(e).__name__}")
            raise



    @classmethod
    def init_task_volc_config(cls):
        logger.info("init_task_volc_config")
        try:
            _client = get_nacos_client()
            if _client is None:
                logger.error("Nacos client is not initialized")
                init_nacos()
                _client = get_nacos_client()

            volc_config_name = "volc_config"
            logger.info(f"init volc_config_name: {volc_config_name}")
            # 增加Nacos请求调试日志
            logger.info(f"Requesting config from Nacos: data_id={volc_config_name}, group={_group}, server={get_nacos_client()._server_addrs if hasattr(get_nacos_client(), '_server_addrs') else 'unknown'}")
            volc_config = _client.get_config(data_id=volc_config_name, group=_group)
            # 验证响应内容
            if not volc_config:
                logger.warning(f"Received empty config for {volc_config_name} from Nacos")
            logger.info(f"init volc_config: {volc_config}")
            cls.volc_config_change_callback({"content": volc_config})
            logger.info(f"do volc_config_change_callback")
            _client.add_config_watcher(data_id=volc_config_name, group=_group,
                                                  cb=cls.volc_config_change_callback)
            logger.info(f"do add_config_watcher")
        except EOFError as e:   
            logger.error(f"EOFError: {e}")
            raise

        except Exception as e:
            logger.error(f"Failed to initialize volc_config (data_id: 'volc_config', group: '{_group}'): {str(e)} | Error type: {type(e).__name__}")
            raise

    

    @classmethod
    def get_volc_config(cls):
        return cls._volc_config

    

    @classmethod
    def volc_config_change_callback(cls, config):
        try:
            config_content = config['content']
            config_data = yaml.load(config_content, Loader=yaml.FullLoader)
            cls._volc_config = config_data
        except Exception as e:
            logger.warning(f"volc_config_change_error: {e}")

    