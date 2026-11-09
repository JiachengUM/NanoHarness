"""
来自https://www.volcengine.com/docs/84313/1952263?lang=zh
连包的名字volcenginesdkvikingdb都是错的，在其它包（如vikingdb）中也找不到这个名字。也是服了。
"""
import volcenginesdkcore
import volcenginesdkvikingdb
from volcenginesdkcore.rest import ApiException
from volcenginesdkvikingdb import CreateCollectionForMemoryRequest, CreateCollectionForMemoryResponse

host="vikingdb.cn-beijing.volcengineapi.com"
# 全局设置
configuration = volcenginesdkcore.Configuration()
configuration.ak =  "your_ak"
configuration.sk = "your_sk"
configuration.debug = True
configuration.host = host
configuration.region = "cn-beijing"
configuration.scheme="https"
configuration.client_side_validation = True
volcenginesdkcore.Configuration.set_default(configuration)
api_instance = volcenginesdkvikingdb.VIKINGDBApi()
try:
    body = CreateCollectionForMemoryRequest(
        collection_name="my_first_memory_collection",
        description="test description",
        builtin_event_types=["sys_event_v1"],
        builtin_profile_types=["sys_profile_v1"]
    )
    res:CreateCollectionForMemoryResponse = api_instance.create_collection_for_memory(body)
    print(res.to_dict())
except ApiException as e:
    print(f"API异常: {e}")
    pass