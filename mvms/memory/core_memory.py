"""Core Memory 模块：简化版核心记忆管理"""

from pydantic import BaseModel, Field
from jinja2 import Template

# 全局常量：记忆编译模板
PROMPT_TEMPLATE = """{% for label, block in blocks.items() %}
<{{ label }}>
{{ block.value }}
</{{ label }}>
{% endfor %}"""


class MemoryBlock(BaseModel):
    label: str = Field(..., description="记忆块唯一标签（如 'persona', 'human', 'tasks'）")
    value: str = Field(default="", max_length=3000, description="记忆块内容（最大3000字符）")
    read_only: bool = Field(default=False, description="是否只读（只读块无法修改内容）")
    description: str = Field(default="", description="记忆块用途说明（区别于label：label是标识，description是解释）")


class CoreMemory(BaseModel):
    """仅保留核心操作"""
    # 记忆块存储：使用列表存储MemoryBlock实例
    blocks: list[MemoryBlock] = Field(default_factory=list, description="记忆块列表")

    def add_block(self, label: str, value: str = "", **kwargs) -> MemoryBlock:
        """添加记忆块：确保label唯一，支持自定义read_only等参数"""
        if any(b.label == label for b in self.blocks):
            return self.get_block(label)  # 如果已存在，直接返回现有块
        
        block = MemoryBlock(label=label, value=value, **kwargs)
        self.blocks.append(block)
        return block

    def get_block(self, label: str) -> MemoryBlock | None:
        """获取记忆块：不存在则返回None"""
        return next((b for b in self.blocks if b.label == label), None)

    def update_block_value(self, label: str, value: str) -> None:
        """全量更新记忆块内容：支持覆盖式修改"""
        block = self.get_block(label)
        if block is None:
            # 如果不存在，创建一个新的
            self.add_block(label, value)
            return
        if block.read_only:
            return  # 只读块直接跳过，不报错
        block.value = value

    def compile_to_prompt(self) -> str:
        """编译记忆为LLM提示词供模板使用"""
        blocks_dict = {block.label: block for block in self.blocks}
        return Template(PROMPT_TEMPLATE).render(blocks=blocks_dict)
