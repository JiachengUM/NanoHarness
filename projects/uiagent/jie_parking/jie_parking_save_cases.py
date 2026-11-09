from server.model.log import LogTable

from projects.uiagent.server.configs.config import AppConfig
from projects.uiagent.server.configs.init_database import init_engine
from projects.uiagent.server.configs.nacos_configs import NacosConfigs

init_nacos()
await NacosConfigs.init()
await AppConfig.init()
await init_engine(AppConfig.DATABASE_URL)
# data = await LogTable.get_log_data(
#     trace_id = '2c85ab31-dde3-415e-b95b-4b19bc9904ec'
# )
# print(data)
await LogTable.trace_id_to_datasets(
    # "7fd35a31-da40-42cc-bdd3-9c262cedcdf0",
    chat_id="79759ae110824be1a5f3d870a9376970",
    save_dir=r"D:\Projects\nanoai\projects\uiagent\jie_parking\datasets\bad_case_with_xml\79759ae110824be1a5f3d870a9376970",
)
await close_db()
)
await close_db()
