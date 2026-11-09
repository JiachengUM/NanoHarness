import logging
from typing import Dict, Optional

import yaml
from asgiref.sync import sync_to_async

from projects.uiagent.server.configs.nacos_util import get_nacos_client

logger = logging.getLogger('nacos')
logger.setLevel(logging.CRITICAL)
_group = "DEFAULT_GROUP"


class NacosConfigs:
    _api_key_config: Dict
    _alert_config: Dict
    _device_config: Dict

    @classmethod
    async def init(cls):
        init_api_key_config = sync_to_async(cls.init_task_api_key_config)
        await init_api_key_config()

    @classmethod
    def init_task_api_key_config(cls):
        try:
            api_key_config_name = "REDACTED"
            api_key_config = get_nacos_client().get_config(data_id=api_key_config_name, group=_group)
            cls.api_key_config_change_callback({"content": api_key_config})
            get_nacos_client().add_config_watcher(data_id=api_key_config_name, group=_group,
                                                  cb=cls.api_key_config_change_callback)
        except Exception as e:
            logger.error(f"Failed to initialize api_key_config: {e}")
            raise


    @classmethod
    def get_api_key_config(cls):
        return cls._api_key_config

    @classmethod
    def api_key_config_change_callback(cls, config):
        try:
            config_content = config['content']
            config_data = yaml.load(config_content, Loader=yaml.FullLoader)
            cls._api_key_config = config_data
        except Exception as e:
            logger.warning(f"api_key_config_change_error: {e}")

