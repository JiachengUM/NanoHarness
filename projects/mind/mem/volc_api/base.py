from pydantic import BaseModel, Field, model_validator

# 唯一定位记忆库
class CollectionID(BaseModel):
    """
    记忆库唯一标识符.通过resource_id唯一指定的资源id, 或者同时声明collection_name和project_name和session.CollectionID相同。
    """

    collection_name: str | None = Field(default=None, description="目标记忆库的名称")
    
    project_name: str | None = Field(default="default", description="记忆库所属项目，默认为 'default'")
    
    resource_id: str | None = Field(default=None, description="记忆库唯一的资源 id。可选择直接传 resource_id, 或同时传 collection_name 和 project_name")

    @model_validator(mode="after")
    def check_collection_id(self):
        """校验记忆库唯一标识符"""
        if not self.resource_id and not (self.collection_name and self.project_name):
            raise ValueError("必须提供 resource_id 或同时提供 collection_name 和 project_name")

        return self

# 所有接口返回必有的要素，额外有data的需要继承这个类实现
class StandardResponse(BaseModel):
    '''火山记忆相关接口标准响应'''
    code: int = Field(..., description="状态码，0 表示成功，其他表示错误。")

    message: str = Field(..., description="返回信息, 成功时为'success'")

    request_id: str = Field(..., description="标识每个请求的唯一ID。")

# 事件和画像的内容格式约束都是一致的，需要支持None
MemoryContentType = str | list[str] | int | list[int] | float | bool | None