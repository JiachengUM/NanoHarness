from pydantic import BaseModel, Field

from nanoai.task.engine import LMWorker
from pydantic import BaseModel, Field

from .core_memory import CoreMemory

class MemoryUpdate(BaseModel):
    """记忆更新指令"""
    block: str = Field(..., description="记忆块名称")
    new_content: str = Field(..., description="完整的整合内容（包含现有信息和新信息，避免重复）")
    reason: str = Field(default="LLM分析", description="更新原因和依据")

class MemoryAnalysisResult(BaseModel):
    updates: list[MemoryUpdate] = Field(default_factory=list, description="记忆更新指令列表")

class MemoryManager:
    """简化的记忆管理器：只保留核心功能"""    
    
    def __init__(self, *, core_memory: CoreMemory, batch_size: int = 3, enable_llm_analysis: bool = True):
        # 使用传入的CoreMemory实例，避免重复创建
        self.core_memory = core_memory
        
        # 创建记忆分析任务Worker
        self.memory_worker = LMWorker(
            "你是一个记忆分析专家，负责分析对话内容并智能地更新记忆。",
            MemoryAnalysisResult,  # 添加必需的output_type参数
            timeout=60
        )

        self.conversation_history: list[tuple[str, str]] = []
        '''"对话历史，用于LLM分析"'''

        self.batch_size: int = batch_size        # LLM分析前的对话批处理大小
        self.enable_llm_analysis: bool = enable_llm_analysis # 是否启用LLM分析

    # ==================== 状态管理方法 ====================
    
    def save_state(self) -> dict:
        """保存记忆状态"""
        return {
            "conversation_history": self.conversation_history,
            "batch_size": self.batch_size,
            "enable_llm_analysis": self.enable_llm_analysis,
        }
    
    def load_state(self, state: dict):
        """加载记忆状态"""
        if "conversation_history" in state:
            self.conversation_history = state["conversation_history"]
        
        if "batch_size" in state:
            self.batch_size = state["batch_size"]
        
        if "enable_llm_analysis" in state:
            self.enable_llm_analysis = state["enable_llm_analysis"]
    
    # ==================== 对话管理方法 ====================
    
    def add_conversation(self, user_input: str, assistant_response: str) -> None:
        """添加对话到历史"""
        self.conversation_history.append((user_input,assistant_response))
        
        # 如果未达到批处理大小，什么也不做
        if len(self.conversation_history) < self.batch_size:
            return
        
        if not self.enable_llm_analysis:
            return
        
        """llm分析对话并更新记忆"""
        analysis_prompt = self._build_analysis_prompt()
            
        try:
            result = self.memory_worker.execute(analysis_prompt)
        except Exception as e:
            print(f"LLM分析失败: {e}")
            return
            
        # 更新memory
        for update in result.updates:
            block = update.block
            new_content = update.new_content
            if not self.core_memory.get_block(block):
                self.core_memory.add_block(block, "")
            
            # 获取记忆块并检查只读状态
            memory_block = self.core_memory.get_block(block)
            if memory_block.read_only:
                print(f"[WARNING] 记忆块[{block}]是只读的，跳过更新")
                continue
            
            # 使用完整内容替换（LLM已经整合了现有信息和新信息）
            self.core_memory.update_block_value(block, new_content)        
        
        # 清空对话历史
        self.conversation_history.clear()
    
    def _build_analysis_prompt(self) -> str:
        """构建通用的记忆分析提示"""
        current_memory = self.core_memory.compile_to_prompt()
        conversation_text = "\n".join([
            f"第{i}轮对话:\n[用户] {conv[0]}\n[AI助手] {conv[1]}\n"
            for i, conv in enumerate(self.conversation_history, 1)
        ])
        # 获取所有记忆块的标签
        blocks_info = "\n".join([f"- {block.label}: {block.description or '无描述'}" for block in self.core_memory.blocks])
        
        return f"""
你是 NanoAI 的记忆分析专家，负责智能地更新和管理智能体的核心记忆。

当前记忆状态:
{current_memory}

可用记忆块:
{blocks_info}

对话历史:
{conversation_text}

你的任务是通过分析对话内容，智能地更新记忆。请遵循以下原则：

1. **基础人物事实留存**：识别用户身份信息、昵称、说话风格等，永久留存无需重复确认
2. **基于偏好推荐**：识别用户的历史偏好、推荐内容，增强"懂我"感
3. **行为习惯个性响应**：识别用户的操作习惯、交互模式、个性特征等

分析指导：
- **user_facts**: 识别用户的基础身份信息、昵称、说话风格、职业背景等
- **preferences**: 识别用户的内容偏好、推荐需求、兴趣方向等
- **behavior_patterns**: 识别用户的操作习惯、交互模式、个性特征等

重要提醒：
- **严格区分用户和AI助手的信息**：只记录用户的信息，不要记录AI助手的名字、角色、能力等
- **user_facts中只能包含用户的信息**：如用户姓名、年龄、职业、居住地等
- **不要混淆角色**：AI助手的名字（如"小游"）不是用户的昵称
- **仔细分析对话内容**：确保提取的信息确实来自用户的表达，而不是AI助手的回复

请按以下格式输出更新指令（直接返回JSON，不要包含代码块标记）：

{{
    "updates": [
        {{
            "block": "记忆块名称",
            "new_content": "完整的整合内容（包含现有信息和新信息，避免重复）",
            "reason": "更新原因和依据"
        }}
    ]
}}

如果没有需要更新的信息，输出：
{{"updates": []}}

注意：
- 只更新真正需要更新的记忆块
- **new_content应该是完整的整合内容，不是追加内容**
- **将新信息与现有信息智能整合，避免重复表达**
- 保持内容的自然性和可读性
- 确保更新后的内容对后续对话有帮助
- 考虑记忆块之间的关联性
- **直接返回JSON格式，不要包含```json```代码块标记**
"""
