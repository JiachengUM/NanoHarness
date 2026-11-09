from pydantic import BaseModel, Field


class RewriteCategory(BaseModel):
    name: str = Field(..., title="改写类别名称", description="改写类别名称")
    description: str = Field(..., title="改写类别描述", description="关于改写类别的定义和描述")
    examples: list[str] = Field(..., title="改写类别示例", description="改写类别示例")
    notices: list[str] | None = Field(default=None, title="注意事项", description="为了理解改写类别的注意事项")

class IntentCategory(BaseModel):
    name: str = Field(..., title="意图类别名称", description="意图类别名称")
    description: str = Field(..., title="用户意图描述", description="关于用户意图的定义和描述")
    examples: list[str] = Field(..., title="用户消息示例", description="用户消息示例")
    notices: list[str] | None = Field(default=None, title="注意事项", description="为了理解用户意图的注意事项")


# base category instances, 只包含name, description
car_control_categories = [
    IntentCategory("空调"),
    IntentCategory("音响"),
]

car_knowledge_categories = [
    IntentCategory("车辆行驶安全"),
    IntentCategory("车辆保养"),
    IntentCategory("车辆维修"),
    IntentCategory("车辆保险"),
    IntentCategory("车辆购置"),
    IntentCategory("车辆租赁"),
    IntentCategory("车辆驾驶技巧"),
    IntentCategory("车辆驾驶安全"),
    IntentCategory("车辆驾驶技巧"),
]


# 改写类别（其实不需要，因为已经定义了RewriteType）
rewrite_categories = [
    RewriteCategory("指代"),
    RewriteCategory("省略"),
    RewriteCategory("澄清"),
    RewriteCategory("模糊"),
]

"""
两个模版，一个是多轮对话，一个是改写，两个模版不需要设计到domain，只涉及到subcategory
多轮对话模版，不涉及到任何改写，只是上下文通顺的一段对话，这里为了保证对话的流畅、合理、多样
可以使用一些硬编码，比如可以规定从同一个domain的一个subcategory自然的过渡到另一个subcategory
"""

Context_Dialogue_Template = """
你是一个专业的语料生成专家。
请先生成关于"{{ sub_category }}"的单轮提问。

【子类说明】
{{ sub_category }}：{{ sub_category_description }}

给一个回答
从一个"{{ sub_category }}"的自然过渡到另一个"{{ sub_category }}"，给出一个提问
再给一个回答

"""


Rewrite_Dialogue_Template = f"""
你是一个专业的语料生成专家。
从{rewrite_categories}中选择一个改写类别，生成一个改写后的提问。
"""


# 生成数据阶段，examples and notices会非常详细

# more category instances derived from base categories
# car_control_categories["空调"].examples = load_config_file()

# 算法阶段，examples and notices需要简单
# category instances from base instances


if __name__ == "__main__":
    print(car_control_categories)

