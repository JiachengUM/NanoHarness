from pydantic import BaseModel, Field

__all__ = [
    "IntentCategory",
    "IntentCategoryLike",
]

class IntentCategory(BaseModel):
    name: str = Field(..., title="意图类别名称", description="意图类别名称")
    '''需要很简明。'''

    definition: str = Field(..., title="意图类别定义", description="意图类别的准确定义")
    '''需要在抽象和精确之间平衡, 不要包括具体的示例。'''
    
    example: str | list[str] | None = Field(..., title="典型的正例", description="典型的正例")
    '''
    需要有多样性和代表性，能把类别的边界大致勾勒出来。
    支持多种类型是为了兼容不同的数据格式, 便于使用。可以为None，但通常需要具体的值，因此不支持缺省值。
    写法非常灵活。写的好的话, 其实不怎么需要下面的examples_neg和notice字段。
    '''

    example_neg: str | list[str] | None = Field(default=None, title="典型的负例", description="典型的负例")
    '''
    可选。
    支持多种类型是为了兼容不同的数据格式, 便于使用。
    '''
    
    notice: str | list[str] | None = Field(default=None, title="其它注意事项", description="关于如何区分是否属于该类别的其它注意事项")
    '''
    可选。
    支持多种类型是为了兼容不同的数据格式, 便于使用。
    '''


IntentCategoryLike = str | IntentCategory
'''意图类别的类型定义。非常通用，会持续扩充支持各种类型。很重要，要谨慎。'''
