'''该模块定义对话数据结构极其相关功能。主要用于对话数据管理。它和其它的模块尽量解耦，如对话生成，业务逻辑等。'''

import json
from typing import Any

from pydantic import BaseModel, Field

from nanoai.utils.text_utils import (
    get_theme_css, 
    merge_styling, 
    Theme
)

class Round(BaseModel):
    '''一轮对话的数据。'''

    message_a: str = Field(..., description="A方的消息")
    think_a: str | None = Field(default=None, description="A方的思考")
    message_b: str = Field(..., description="B方的消息")
    think_b: str | None = Field(default=None, description="B方的思考")

    def format(self, name_a: str, name_b: str, think_prefix: str) -> str:
        '''格式化一轮对话。
        TODO: 需要改成 __nl_repr__么？ 没想好。
        '''

        s = ""

        if self.think_a is not None:
            s += f"{name_a}({think_prefix}): {self.think_a}\n"

        s += f"{name_a}: {self.message_a}\n"

        if self.think_b is not None:
            s += f"{name_b}({think_prefix}): {self.think_b}\n"

        s += f"{name_b}: {self.message_b}\n"

        return s


class Conversation(list[Round]):
    '''对话的数据。它和model.messages.QAList类似。但语义层级位于chat层，更接近业务。
    TODO: name_a(b) 需要存在这里么？
    '''

    def format(self, name_a: str = "用户", name_b: str = "助手", think_prefix: str = "内心独白") -> str:
        '''格式化对话。'''
        # 在每轮前加上 (Rn)
        return "\n".join(
            [f"(R{idx+1})\n{round.format(name_a, name_b, think_prefix)}" for idx, round in enumerate(self)]
        )
    
    def to_json(self, filename: str) -> None:
        """将对话保存为JSON文件"""
        data = [round.model_dump() for round in self]
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    
    @classmethod
    def from_json(cls, filename: str) -> 'Conversation':
        """从JSON文件加载对话"""
        with open(filename, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        rounds = [Round(**round_data) for round_data in data]
        return cls(rounds)
    
    def to_html(
        self,
        filename: str,
        title: str,
        scenario: str,
        user_info: str,
        topic: str,
        styling: dict[str, Any] | None = None,
        name_a: str = "用户",
        name_b: str = "助手",
        show_thinking: bool = True
    ) -> None:
        """将对话转换为HTML文件
        
        Args:
            filename: 输出的HTML文件路径
            title: HTML页面标题
            scenario: 对话场景
            user_info: 用户信息
            topic: 对话主题
            styling: 样式配置字典，支持以下键：
                - theme_color: 主题颜色
                - border_radius: 边框圆角
                - container_width: 容器宽度 (如 "800px", "90%")
                - chat_width: 对话区域宽度 (如 "700px", "85%")
                - min_width: 最小宽度 (如 "600px")
            name_a: A方名称（通常是用户）
            name_b: B方名称（通常是AI助手）
            show_thinking: 是否显示思考内容
        """
        conversation_to_html(
            self, filename, title, scenario, user_info, topic, 
            styling, name_a, name_b, show_thinking
        )


def generate_conversation_content(
    conversation: Conversation, 
    scenario: str, 
    user_info: str, 
    topic: str,
    name_a: str = "用户",
    name_b: str = "助手",
    show_thinking: bool = True
) -> str:
    """生成对话的HTML内容"""
    
    def format_text(text: str) -> str:
        """格式化文本，处理换行符和特殊字符"""
        if not text:
            return ""
        # 将换行符转换为HTML的<br>标签
        # 同时转义HTML特殊字符，防止XSS
        import html
        escaped_text = html.escape(text)
        return escaped_text.replace('\n', '<br>')
    
    # 生成头部信息 - 使用 name_a 而不是硬编码"用户"
    header = f"""
    <div class="chat-header">
        <h4>💬 对话信息</h4>
        <p><strong>场景：</strong>{scenario}</p>
        <p><strong>{name_a}：</strong>{user_info}</p>
        <p><strong>主题：</strong>{topic}</p>
    </div>
    """
    
    # 生成对话内容
    messages_html = '<div class="chat-messages">'
    
    # 在对话区域顶部添加名称标签
    messages_html += f"""
    <div class="names-header">
        <div class="name-tag assistant-name">{name_b}</div>
        <div class="name-tag user-name">{name_a}</div>
    </div>
    """
    
    for i, round_data in enumerate(conversation):
        thinking_a = f'<div class="thinking">💭 {format_text(round_data.think_a)}</div>' if show_thinking else ''
        thinking_b = f'<div class="thinking">💭 {format_text(round_data.think_b)}</div>' if show_thinking else ''
        
        messages_html += f"""
        <div class="round" data-round="{i+1}">
            <div class="message user-message">
                <div class="bubble">
                    <div class="content">{format_text(round_data.message_a)}</div>
                    {thinking_a}
                </div>
            </div>
            
            <div class="message assistant-message">
                <div class="bubble">
                    <div class="content">{format_text(round_data.message_b)}</div>
                    {thinking_b}
                </div>
            </div>
        </div>
        """
    messages_html += '</div>'
    
    return header + messages_html


def generate_conversation_css(styling: dict) -> str:
    """生成对话的CSS样式"""
    theme_color = styling.get("theme_color", get_theme_css(Theme.BLUE))
    border_radius = styling.get("border_radius", "8px")
    container_width = styling.get("container_width", "100%")
    chat_width = styling.get("chat_width", "800px")
    min_width = styling.get("min_width", "600px")
    
    return f"""
        .chat-header {{
            background: {theme_color};
            color: white;
            padding: 20px;
            border-radius: {border_radius};
            margin-bottom: 30px;
        }}
        .chat-header h4 {{
            margin-bottom: 15px;
            font-weight: 600;
        }}
        .chat-header p {{
            margin-bottom: 8px;
            font-size: 14px;
        }}
        .chat-messages {{
            max-width: {chat_width};
            width: {chat_width};
            min-width: {min_width};
            margin: 0 auto;
        }}
        .names-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
            padding: 15px;
            background-color: #f8f9fa;
            border-radius: {border_radius};
            border: 1px solid #dee2e6;
        }}
        .name-tag {{
            padding: 8px 16px;
            border-radius: 20px;
            font-size: 14px;
            font-weight: 600;
            text-align: center;
            min-width: 80px;
        }}
        .user-name {{
            background-color: #e3f2fd;
            border: 2px solid #2196f3;
            color: #1976d2;
        }}
        .assistant-name {{
            background-color: #f3e5f5;
            border: 2px solid #9c27b0;
            color: #7b1fa2;
        }}
        .round {{
            margin-bottom: 30px;
        }}
        .message {{
            margin-bottom: 20px;
            display: flex;
            align-items: flex-start;
        }}
        .user-message {{
            justify-content: flex-end;
        }}
        .assistant-message {{
            justify-content: flex-start;
        }}
        .bubble {{
            max-width: 70%;
            padding: 12px 16px;
            border-radius: 18px;
            position: relative;
            word-wrap: break-word;
        }}
        .user-message .bubble {{
            background-color: #007bff;
            color: white;
            margin-left: 20px;
        }}
        .assistant-message .bubble {{
            background-color: #e9ecef;
            color: #495057;
            margin-right: 20px;
        }}
        .thinking {{
            font-size: 0.85em;
            opacity: 0.7;
            margin-top: 8px;
            font-style: italic;
        }}
        .content {{
            line-height: 1.5;
        }}
        /* 响应式设计 */
        @media (max-width: 768px) {{
            .chat-messages {{
                width: 95%;
                max-width: 95%;
                min-width: auto;
            }}
            .bubble {{
                max-width: 85%;
            }}
            .names-header {{
                flex-direction: column;
                gap: 10px;
                padding: 12px;
            }}
            .name-tag {{
                font-size: 12px;
                padding: 6px 12px;
                min-width: 60px;
            }}
        }}
    """


def conversation_to_html(
    conversation: Conversation,
    filename: str,
    title: str,
    scenario: str,
    user_info: str,
    topic: str,
    styling: dict[str, Any] | None = None,
    name_a: str = "用户",
    name_b: str = "助手",
    show_thinking: bool = True
) -> None:
    """将对话转换为HTML文件
    
    Args:
        conversation: 对话对象
        filename: 输出的HTML文件路径
        title: HTML页面标题
        scenario: 对话场景
        user_info: 用户信息
        topic: 对话主题
        styling: 样式配置字典，支持以下键：
            - theme_color: 主题颜色 (CSS渐变或颜色值)
            - border_radius: 边框圆角 (如 "8px", "12px")
            - container_width: 容器宽度 (如 "800px", "90%", "1200px")
            - chat_width: 对话区域宽度 (如 "700px", "85%", "1000px")
            - min_width: 最小宽度 (如 "600px", "500px")
        name_a: A方名称（通常是用户）
        name_b: B方名称（通常是AI助手）
        show_thinking: 是否显示思考内容
    
    Examples:
        # 基本使用
        conversation.to_html(
            filename="chat.html",
            title="对话记录",
            scenario="技术支持",
            user_info="张三",
            topic="系统故障排查"
        )
        
        # 自定义主题颜色
        conversation.to_html(
            filename="chat_green.html",
            title="绿色主题对话",
            scenario="学习咨询",
            user_info="李四",
            topic="Python学习",
            styling={"theme_color": "linear-gradient(135deg, #28a745 0%, #20c997 100%)"}
        )
        
        # 设置固定宽度（适合桌面端）
        conversation.to_html(
            filename="chat_desktop.html",
            title="桌面端对话",
            scenario="项目讨论",
            user_info="团队",
            topic="需求分析",
            styling={
                "container_width": "1200px",
                "chat_width": "900px",
                "min_width": "800px",
                "theme_color": "linear-gradient(135deg, #fd7e14 0%, #ffc107 100%)"
            }
        )
        
        # 设置百分比宽度（适合响应式）
        conversation.to_html(
            filename="chat_responsive.html",
            title="响应式对话",
            scenario="在线咨询",
            user_info="访客",
            topic="产品介绍",
            styling={
                "container_width": "95%",
                "chat_width": "90%",
                "min_width": "600px",
                "border_radius": "12px"
            }
        )
        
        # 窄屏设置（适合移动端）
        conversation.to_html(
            filename="chat_mobile.html",
            title="移动端对话",
            scenario="移动咨询",
            user_info="移动用户",
            topic="快速问答",
            styling={
                "container_width": "100%",
                "chat_width": "95%",
                "min_width": "400px",
                "theme_color": "linear-gradient(135deg, #6f42c1 0%, #e83e8c 100%)"
            }
        )
        
        # 使用预设主题
        from nanoai.utils.text_utils import Theme, get_theme_css
        conversation.to_html(
            filename="chat_blue.html",
            title="蓝色主题对话",
            scenario="商务会议",
            user_info="客户",
            topic="合作洽谈",
            styling={
                "theme_color": get_theme_css(Theme.BLUE),
                "container_width": "1000px",
                "chat_width": "800px"
            }
        )
    
    Notes:
        - 宽度单位支持 px（像素）、%（百分比）、em、rem 等CSS单位
        - 主题颜色支持CSS渐变、十六进制颜色、RGB等格式
        - 响应式设计：当屏幕宽度小于768px时，会自动调整为移动端布局
        - 思考内容（thinking）默认显示，可通过show_thinking=False隐藏
        - 所有样式参数都有合理的默认值，可以只设置需要的参数
    """
    
    # 设置默认样式
    default_styling = {
        "theme_color": get_theme_css(Theme.BLUE),
        "border_radius": "8px",
        "container_width": "100%",
        "chat_width": "800px",
        "min_width": "600px",
    }
    
    # 合并样式配置
    final_styling = merge_styling(styling or {}, default_styling)
    
    # 生成对话内容
    conversation_content = generate_conversation_content(
        conversation, scenario, user_info, topic, name_a, name_b, show_thinking
    )
    
    # 生成对话CSS
    custom_css = generate_conversation_css(final_styling)
    
    # 组装完整HTML，使用支持宽度的函数
    from nanoai.utils.text_utils import generate_html_document_with_width
    full_html = generate_html_document_with_width(
        title, conversation_content, custom_css, final_styling["container_width"]
    )
    
    # 保存文件（直接内联实现）
    with open(filename, "w", encoding="utf-8") as f:
        f.write(full_html)


class ConversationInfo(BaseModel):
    '''对话信息。'''

    summary: str
    name_a: str
    name_b: str

def conversations_to_html(
    conversations: list[tuple[Conversation, ConversationInfo]],
    filename: str,
    title: str,
    styling: dict[str, Any] | None = None,
    show_thinking: bool = True
) -> None:
    """以HTML文件的形式显示多组对话，方便对它们做对比。
    每组对话显示为一列。其形式和conversation_to_html显示的对话相同。尽量复用其实现。
    每个对话的长度都相同。 因此，每行显示同一轮对话中的多个对话。
    多组对话并列显示。上下位置相同。
    title对对于所有对话的简要总结，显示在文件顶部。
    假设有2组对话，每组对话有3轮。那么它们在html文件中的布局如下：
    |          title              |
    | 对话1的info | 对话2的info    |
    | 对话1的第一轮 | 对话2的第一轮 |
    | 对话1的第二轮 | 对话2的第二轮 |
    | 对话1的第三轮 | 对话2的第三轮 |
    """
    
    if not conversations:
        raise ValueError("conversations列表不能为空")
    
    # 验证所有对话长度相同
    first_length = len(conversations[0][0])
    for conv, _ in conversations:
        if len(conv) != first_length:
            raise ValueError(f"所有对话的长度必须相同，期望{first_length}轮，但发现{len(conv)}轮")
    
    # 设置默认样式
    default_styling = {
        "theme_color": get_theme_css(Theme.BLUE),
        "border_radius": "8px",
        "container_width": "100%",
        "chat_width": "800px",
        "min_width": "600px",
    }
    
    # 合并样式配置
    final_styling = merge_styling(styling or {}, default_styling)
    
    # 生成多对话对比内容
    comparison_content = generate_conversations_comparison_content(
        conversations, show_thinking
    )
    
    # 生成多对话对比CSS
    comparison_css = generate_conversations_comparison_css(final_styling, len(conversations))
    
    # 组装完整HTML
    from nanoai.utils.text_utils import generate_html_document_with_width
    full_html = generate_html_document_with_width(
        title, comparison_content, comparison_css, final_styling["container_width"]
    )
    
    # 保存文件
    with open(filename, "w", encoding="utf-8") as f:
        f.write(full_html)


def generate_conversations_comparison_content(
    conversations: list[tuple[Conversation, ConversationInfo]], 
    show_thinking: bool = True
) -> str:
    """生成多对话对比的HTML内容"""
    
    def format_text(text: str) -> str:
        """格式化文本，处理换行符和特殊字符"""
        if not text:
            return ""
        import html
        escaped_text = html.escape(text)
        return escaped_text.replace('\n', '<br>')
    
    # 生成头部信息
    header = f"""
    <div class="comparison-header">
        <h4>💬 对话对比</h4>
        <p>共 {len(conversations)} 组对话，每组 {len(conversations[0][0])} 轮</p>
    </div>
    """
    
    # 生成对话信息行（水平排列所有对话的ConversationInfo）
    conversations_info_row = '<div class="conversations-info-row">'
    for i, (_, info) in enumerate(conversations):
        conversations_info_row += f"""
        <div class="conversation-info">
            <h5>对话 {i+1}</h5>
            <p class="conversation-summary">{info.summary}</p>
            <div class="participants">
                <span class="participant-a">{info.name_a}</span> vs <span class="participant-b">{info.name_b}</span>
            </div>
        </div>
        """
    conversations_info_row += '</div>'
    
    # 生成对话内容（按轮次生成，每行包含所有对话的同一轮）
    conversations_html = '<div class="conversations-container">'
    
    # 按轮次生成内容
    num_rounds = len(conversations[0][0])
    for round_idx in range(num_rounds):
        conversations_html += f'<div class="round-row" data-round="{round_idx+1}">'
        
        # 为每个对话生成这一轮的内容
        for conv, info in conversations:
            round_data = conv[round_idx]
            
            thinking_a = f'<div class="thinking">💭 {format_text(round_data.think_a)}</div>' if show_thinking else ''
            thinking_b = f'<div class="thinking">💭 {format_text(round_data.think_b)}</div>' if show_thinking else ''
            
            conversations_html += f"""
            <div class="conversation-round">
                <div class="round" data-round="{round_idx+1}">
                    <div class="message user-message">
                        <div class="bubble">
                            <div class="content">{format_text(round_data.message_a)}</div>
                            {thinking_a}
                        </div>
                    </div>
                    
                    <div class="message assistant-message">
                        <div class="bubble">
                            <div class="content">{format_text(round_data.message_b)}</div>
                            {thinking_b}
                        </div>
                    </div>
                </div>
            </div>
            """
        
        conversations_html += '</div>'
    
    conversations_html += '</div>'
    
    return header + conversations_info_row + conversations_html


def generate_conversations_comparison_css(styling: dict, num_conversations: int) -> str:
    """生成多对话对比的CSS样式"""
    theme_color = styling.get("theme_color", get_theme_css(Theme.BLUE))
    border_radius = styling.get("border_radius", "8px")
    container_width = styling.get("container_width", "100%")
    chat_width = styling.get("chat_width", "800px")
    min_width = styling.get("min_width", "300px")  # 大幅减小默认最小宽度
    
    return f"""
        .comparison-header {{
            background: {theme_color};
            color: white;
            padding: 20px;
            border-radius: {border_radius};
            margin-bottom: 30px;
        }}
        .comparison-header h4 {{
            margin-bottom: 15px;
            font-weight: 600;
        }}
        .comparison-header p {{
            margin-bottom: 8px;
            font-size: 14px;
        }}
        .conversations-info-row {{
            display: flex;
            gap: 15px;
            margin-bottom: 30px;
            padding: 20px;
            background-color: #f8f9fa;
            border-radius: {border_radius};
            border: 1px solid #dee2e6;
        }}
        .conversation-info {{
            flex: 1;
            text-align: center;
            padding: 15px;
            background-color: white;
            border-radius: {border_radius};
            border: 2px solid #dee2e6;
            min-width: 0;  /* 允许收缩 */
        }}
        .conversation-info h5 {{
            margin-bottom: 10px;
            color: #495057;
            font-weight: 600;
        }}
        .conversation-summary {{
            font-size: 12px;
            color: #6c757d;
            margin-bottom: 10px;
            line-height: 1.4;
        }}
        .participants {{
            font-size: 11px;
            color: #495057;
        }}
        .participant-a {{
            color: #007bff;
            font-weight: 600;
        }}
        .participant-b {{
            color: #6f42c1;
            font-weight: 600;
        }}
        .conversations-container {{
            width: 100%;
            max-width: {container_width};
            margin: 0 auto;
        }}
        .round-row {{
            display: flex;
            gap: 15px;
            margin-bottom: 40px;
            align-items: flex-start;
        }}
        .conversation-round {{
            flex: 1;
            min-width: {min_width};
            max-width: calc(100% / {num_conversations} - 10px);  /* 确保不超出容器 */
        }}
        .round {{
            margin-bottom: 0;
        }}
        .message {{
            margin-bottom: 15px;
            display: flex;
            align-items: flex-start;
        }}
        .user-message {{
            justify-content: flex-end;
        }}
        .assistant-message {{
            justify-content: flex-start;
        }}
        .bubble {{
            max-width: 90%;  /* 增加最大宽度以适应更窄的列 */
            padding: 10px 14px;
            border-radius: 18px;
            position: relative;
            word-wrap: break-word;
        }}
        .user-message .bubble {{
            background-color: #007bff;
            color: white;
            margin-left: 10px;  /* 减小边距 */
        }}
        .assistant-message .bubble {{
            background-color: #e9ecef;
            color: #495057;
            margin-right: 10px;  /* 减小边距 */
        }}
        .thinking {{
            font-size: 0.8em;
            opacity: 0.7;
            margin-top: 6px;
            font-style: italic;
        }}
        .content {{
            line-height: 1.4;
        }}
        /* 响应式设计 - 调整断点 */
        @media (max-width: 1400px) {{
            .conversations-info-row {{
                gap: 10px;
            }}
            .round-row {{
                gap: 10px;
            }}
            .conversation-round {{
                min-width: 250px;
            }}
        }}
        @media (max-width: 1000px) {{
            .conversations-info-row {{
                flex-direction: column;
                gap: 15px;
            }}
            .round-row {{
                flex-direction: column;
                gap: 15px;
            }}
            .conversation-round {{
                width: 100%;
                min-width: auto;
                max-width: none;
            }}
            .bubble {{
                max-width: 90%;
            }}
        }}
        @media (max-width: 768px) {{
            .conversations-container {{
                width: 95%;
                max-width: 95%;
            }}
            .bubble {{
                max-width: 95%;
            }}
            .conversation-info {{
                padding: 10px;
            }}
            .conversation-summary {{
                font-size: 11px;
            }}
        }}
    """