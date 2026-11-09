import gradio as gr
from typing import Tuple, List

from nanoai.chat.define import ChatTaskGenerator
from nanoai.chat.simulation import SimulatedChatUser, ChatUserInfo, execute_and_print, RealChatUser
from nanoai.chat.worker import ChatWorker
from nanoai.model.messages import QAList
import colorama


class ChatSession:
    """聊天会话管理类 - 仅用于需要保持状态的场景（如Gradio UI）"""

    def __init__(self, ass_worker, user, stream: bool = True, 
                 user_color: str = colorama.Fore.BLUE, assistant_color: str = colorama.Fore.RED):
        self.ass_worker = ass_worker
        self.user = user
        self.stream = stream
        self.conversation = QAList()
        # 保存颜色和名称，避免重复传递参数
        self.user_color = user_color
        self.user_name = user.name
        self.assistant_color = assistant_color
        self.assistant_name = ass_worker.name
        self.assistant_msg = ""
        self.is_initialized = False

    def step(self, user_input: str) -> tuple[str, QAList]:
        """单步推进对话，用于Gradio等UI应用"""
        if not self.is_initialized:
            # 初始化设置
            print(f"\n============={self.ass_worker.name}和{self.user.name}的对话开始。=============")
            self.assistant_msg = self.ass_worker.intro()
            print(f"{self.assistant_color}{self.ass_worker.name}: {self.assistant_msg}")
            self.is_initialized = True

        # 用户输入（对于真实用户，直接使用输入）
        if isinstance(self.user, RealChatUser):
            user_msg = user_input
        else:
            # 对于模拟用户，使用其execute方法
            user_msg = self.user.execute(self.assistant_msg)

        # 助手回复
        self.assistant_msg = execute_and_print(self.ass_worker, user_msg, len(self.conversation) + 1, self.stream, self.assistant_color, self.assistant_name)

        # 记录对话
        self.conversation.append((user_msg, self.assistant_msg))

        return self.assistant_msg, self.conversation

    def reset(self):
        """重置会话状态"""
        self.conversation = QAList()
        self.assistant_msg = ""
        self.is_initialized = False

TASK_DESCS = [
    ("扮演专业医生给患者看病", "40多岁的中年程序员", "脱发"),
    ("职业规划师", "32岁想要转行的程序员", "从传统前后端开发转向智能体开发"),
    ("为小学生提供个性化学习计划", "小学三年级女生，性格害羞，说话紧张。", "如何提高表达能力"),
    ("规划个性化旅游路线", "热爱生活但有点懒的宝妈", "带宝宝出游的注意事项"),
    ("推荐音乐", "IT宅男", "最近比较流行的音乐"),
    ("心理咨询师帮助缓解压力", "25岁刚毕业的职场新人，工作压力大", "如何应对职场焦虑"),
    ("营养师制定健康饮食计划", "30岁上班族，经常加班熬夜", "改善亚健康状态"),
    ("健身教练制定运动计划", "35岁久坐办公室的白领", "减脂塑形"),
    ("理财顾问提供投资建议", "28岁有一定存款的年轻人", "基金投资入门"),
    ("语言学习导师", "20岁大学生，英语基础薄弱", "提高英语口语"),
]


# Gradio UI 实现
def create_gradio_app():
    """创建Gradio聊天应用

    这个函数创建了一个完整的聊天应用界面，包含以下功能：
    1. 预定义任务选择：用户可以从预设的任务中选择，或输入自定义任务
    2. 会话初始化：根据任务描述创建AI助手和模拟用户
    3. 自动对话生成：初始化后自动生成多轮对话，模拟真实对话场景
    4. 手动对话：用户可以输入消息与AI助手继续对话
    5. 对话重置：清空当前对话，重新开始

    数据流说明：
    用户输入 -> UI组件 -> 事件处理函数 -> 业务逻辑 -> 更新UI组件 -> 用户看到结果
    """

    # ==================== 全局状态管理 ====================
    # 这些变量在整个应用运行期间保持状态，用于跟踪当前会话和对话进度
    # 使用global声明，确保所有回调函数都能访问和修改同一份状态
    global session, chat_history, current_round, max_rounds, is_generating
    session = None  # 存储当前的聊天会话对象，包含AI助手和用户
    chat_history = []  # 存储所有对话历史，格式：[用户消息, 助手消息]
    current_round = 0  # 当前已生成的对话轮次（0-3）
    max_rounds = 3  # 最大自动生成轮次
    is_generating = False  # 是否正在自动生成对话的标志

    # ==================== 预定义任务配置 ====================
    # 创建下拉选择框的选项列表，格式："序号. 任务描述"
    task_choices = [f"{i+1}. {task[0]}" for i, task in enumerate(TASK_DESCS)]
    task_choices.insert(0, "自定义任务")  # 在列表开头添加"自定义任务"选项

    def on_task_select(selected_task: str) -> Tuple[str, str, str]:
        """当用户选择预定义任务时的处理函数

        功能：当用户从下拉框选择预定义任务时，自动填充任务描述、用户信息和主题
        输入：selected_task - 用户选择的选项字符串，如"1. 扮演专业医生给患者看病"
        输出：返回三个字符串，分别填充到任务描述、用户信息、主题输入框

        数据流：下拉框选择 -> 解析选项 -> 提取对应数据 -> 填充到输入框
        """
        if selected_task == "自定义任务":
            # 如果选择"自定义任务"，清空所有输入框
            return "", "", ""

        # 解析选择的索引：从"1. 任务描述"中提取数字1，然后减1得到数组索引
        try:
            task_index = int(selected_task.split(".")[0]) - 1
            task_desc, user_info, topic = TASK_DESCS[task_index]  # 从预定义数据中获取对应信息
            return task_desc, user_info, topic
        except (ValueError, IndexError):
            # 如果解析失败，返回空字符串
            return "", "", ""

    def init_session(task_desc: str, user_info: str = "", topic: str = "") -> Tuple[str, List[List[str]]]:
        """初始化聊天会话函数

        功能：根据用户输入的任务描述创建AI助手和模拟用户，准备开始对话
        输入：
            task_desc - 任务描述，如"扮演专业医生给患者看病"
            user_info - 用户信息，如"40多岁的中年程序员"
            topic - 对话主题，如"脱发"
        输出：返回状态消息和空的聊天历史

        数据流：用户点击初始化 -> 创建AI任务 -> 创建助手 -> 创建用户 -> 初始化会话 -> 设置生成标志
        """
        # 使用global声明，表示要修改全局变量
        global session, chat_history, current_round, is_generating

        # 输入验证：检查任务描述是否为空
        if not task_desc.strip():
            return "请输入任务描述", []

        try:
            # 步骤1：生成任务描述
            # 使用AI模型根据用户输入生成详细的任务定义
            print("🔄 正在生成任务描述（这可能需要10-15秒）...")
            task_generator = ChatTaskGenerator()  # 创建任务生成器
            task = task_generator.execute(task_desc)  # 调用AI生成任务
            print("✅ 任务描述生成完成")

            # 步骤2：创建AI助手
            # 根据生成的任务创建聊天助手
            print("🔄 正在创建助手...")
            assistant = ChatWorker(task.as_chat_task(), str)  # 创建助手，输出类型为字符串
            print("✅ 助手创建完成")

            # 步骤3：配置模拟用户
            # 创建模拟用户，用于自动生成对话
            print("🔄 正在配置用户...")
            context = ChatUserInfo(
                user_info=user_info if user_info.strip() else None,  # 用户信息，如果为空则设为None
                topic=topic if topic.strip() else None,  # 对话主题，如果为空则设为None
            )
            user = SimulatedChatUser(assistant, context)  # 创建模拟用户
            print("✅ 用户配置完成")

            # 步骤4：初始化会话
            # 创建聊天会话，管理助手和用户之间的对话
            print("🔄 正在初始化会话...")
            session = ChatSession(assistant, user, stream=False)  # 创建会话，不流式输出
            print("✅ 会话初始化完成")

            # 步骤5：重置状态，准备开始自动生成
            chat_history = []  # 清空聊天历史
            current_round = 0  # 重置轮次计数
            is_generating = True  # 设置生成标志为True，启动自动生成

            print("🎉 会话初始化全部完成，开始生成对话！")
            return "✅ 会话已初始化，开始生成对话...", []
        except Exception as e:
            # 如果任何步骤出错，返回错误信息
            print(f"❌ 初始化失败: {str(e)}")
            return f"❌ 初始化失败: {str(e)}", []

    def auto_generate_round() -> Tuple[str, List[List[str]]]:
        """自动生成下一轮对话函数

        功能：由Gradio定时器自动调用，每次生成一轮对话并更新UI
        输入：无（使用全局状态）
        输出：返回状态消息和更新后的聊天历史

        数据流：定时器触发 -> 检查状态 -> 生成对话 -> 更新历史 -> 返回结果
        """
        # 调试信息：确认函数被调用
        print("🔍 定时器被触发 - auto_generate_round 被调用")

        # 使用global声明，表示要修改全局变量
        global session, chat_history, current_round, is_generating

        # 检查是否应该生成对话
        if session is None or not is_generating or current_round >= max_rounds:
            if current_round >= max_rounds:
                # 如果已达到最大轮次，停止生成
                is_generating = False
                print("🎉 对话生成完成，停止定时器")
                return "🎉 对话生成完成！", chat_history
            print(
                f"⏸️ 定时器检查：session={session is not None}, is_generating={is_generating}, current_round={current_round}"
            )
            return "", chat_history  # 如果条件不满足，返回空结果

        try:
            print(f"🔄 正在生成第 {current_round + 1}/{max_rounds} 轮对话...")

            # 生成一轮对话：调用会话的step方法，传入空字符串让模拟用户自动生成输入
            assistant_output, conversation = session.step("")

            # 更新聊天历史：从会话的完整对话中提取最新一轮
            if conversation and len(conversation) > current_round:
                new_round = conversation[current_round]  # 获取当前轮次的对话
                chat_history.append([str(new_round[0]), str(new_round[1])])  # 添加到聊天历史
                current_round += 1  # 轮次计数加1

                print(f"✅ 第 {current_round}/{max_rounds} 轮对话生成完成")
                return f"正在生成第 {current_round}/{max_rounds} 轮对话...", chat_history

        except Exception as e:
            # 如果生成失败，停止生成并返回错误信息
            print(f"❌ 对话生成失败: {e}")
            is_generating = False
            return f"❌ 对话生成失败: {e}", chat_history

        return "🎉 对话生成完成！", chat_history

    def chat_step(user_input: str) -> Tuple[str, List[List[str]]]:
        """处理用户手动输入的函数

        功能：当用户手动输入消息时，让AI助手回复，并更新对话历史
        输入：user_input - 用户输入的消息
        输出：返回空字符串（清空输入框）和更新后的聊天历史

        数据流：用户输入 -> 调用会话step方法 -> 获取AI回复 -> 更新历史 -> 返回结果
        """
        # 使用global声明，表示要访问全局变量
        global session

        # 检查是否已初始化会话
        if session is None:
            return "请先初始化会话", []

        # 检查输入是否为空
        if not user_input.strip():
            return "", []

        try:
            # 调用会话的step方法，传入用户输入，获取AI助手的回复
            assistant_output, conversation = session.step(user_input)

            # 将完整的对话历史转换为Gradio Chatbot格式
            local_chat_history: List[List[str]] = []
            for user_msg, ass_msg in conversation:
                local_chat_history.append([user_msg, ass_msg])  # 格式：[用户消息, 助手消息]

            return "", local_chat_history  # 返回空字符串清空输入框
        except Exception as e:
            return f"对话出错: {str(e)}", []

    def reset_chat() -> Tuple[str, List[List[str]]]:
        """重置对话函数

        功能：清空当前对话，重置所有状态，准备重新开始
        输入：无
        输出：返回重置消息和空的聊天历史

        数据流：用户点击重置 -> 重置会话状态 -> 清空历史 -> 重置计数器 -> 返回结果
        """
        # 使用global声明，表示要修改全局变量
        global session, chat_history, current_round, is_generating

        if session:
            session.reset()  # 重置会话状态
        chat_history = []  # 清空聊天历史
        current_round = 0  # 重置轮次计数
        is_generating = False  # 停止自动生成
        return "对话已重置", []

    # ==================== 创建Gradio界面 ====================
    # 使用gr.Blocks创建界面，Blocks比Interface更灵活，可以创建复杂的布局
    with gr.Blocks(title="NanoAI 聊天应用") as demo:
        # 页面标题和说明
        gr.Markdown("# 🤖 NanoAI 聊天应用")
        gr.Markdown("选择预定义任务或输入自定义任务，然后开始对话！")

        # 使用gr.Row创建水平布局，包含左右两列
        with gr.Row():
            # 左侧列：控制面板（占1份宽度）
            with gr.Column(scale=1):
                # 预定义任务选择下拉框
                task_selector = gr.Dropdown(
                    choices=task_choices,  # 选项列表
                    value="自定义任务",  # 默认值
                    label="选择预定义任务",  # 标签
                    info="选择预定义任务或自定义任务",  # 提示信息
                )

                # 任务描述输入框
                task_desc = gr.Textbox(
                    label="任务描述", placeholder="例如：扮演专业医生给患者看病", lines=2  # 占位符文本  # 2行高度
                )

                # 用户信息输入框
                user_info = gr.Textbox(label="用户信息（可选）", placeholder="例如：40多岁的中年程序员", lines=2)

                # 对话主题输入框
                topic = gr.Textbox(label="对话主题（可选）", placeholder="例如：脱发", lines=1)  # 1行高度

                # 初始化按钮
                init_btn = gr.Button("🚀 初始化会话", variant="primary")  # primary样式，蓝色
                reset_btn = gr.Button("重置对话")  # 默认样式

            # 右侧列：聊天界面（占2份宽度）
            with gr.Column(scale=2):
                # 状态显示框
                status_text = gr.Textbox(
                    label="状态",
                    value="请选择预定义任务或输入自定义任务，然后点击初始化会话（首次初始化可能需要15-20秒，请耐心等待）",
                    interactive=False,  # 不可编辑
                )

                # 聊天机器人界面
                chatbot = gr.Chatbot(label="对话历史", height=400)  # 固定高度400像素

                # 用户输入框
                user_input = gr.Textbox(label="用户输入", placeholder="请输入您的消息...", lines=2)

                # 发送按钮
                send_btn = gr.Button("发送", variant="primary")

        # ==================== 事件绑定 ====================
        # 将UI组件与处理函数绑定，实现交互功能

        # 绑定1：任务选择下拉框变化事件
        # 当用户选择预定义任务时，自动填充其他输入框
        task_selector.change(
            on_task_select,  # 处理函数
            inputs=[task_selector],  # 输入组件
            outputs=[task_desc, user_info, topic],  # 输出组件（要更新的组件）
        )

        # 绑定2：初始化按钮点击事件
        # 当用户点击初始化按钮时，创建会话并开始自动生成对话
        init_btn.click(
            init_session,  # 处理函数
            inputs=[task_desc, user_info, topic],  # 输入组件
            outputs=[status_text, chatbot],  # 输出组件
        )

        # 绑定3：自动生成对话定时器（暂时注释掉）
        # demo.load(auto_generate_round, outputs=[status_text, chatbot], every=3)

        # 添加一个简单的测试定时器，确认定时器机制是否工作
        def test_timer():
            print("⏰ [test_timer] 定时器被调用！")
            return "定时器工作正常", []

        # 测试定时器，每5秒执行一次
        demo.load(test_timer, outputs=[status_text, chatbot], every=5)

        # 绑定4：发送按钮点击事件
        # 当用户点击发送按钮时，处理用户输入并显示AI回复
        send_btn.click(
            chat_step,  # 处理函数
            inputs=[user_input],  # 输入组件
            outputs=[user_input, chatbot],  # 输出组件（清空输入框，更新聊天历史）
        )

        # 绑定5：用户输入框回车事件
        # 当用户在输入框中按回车键时，等同于点击发送按钮
        user_input.submit(
            chat_step, inputs=[user_input], outputs=[user_input, chatbot]  # 处理函数  # 输入组件  # 输出组件
        )

        # 绑定6：重置按钮点击事件
        # 当用户点击重置按钮时，清空所有对话和状态
        reset_btn.click(reset_chat, outputs=[status_text, chatbot])  # 处理函数  # 输出组件

    # 返回创建的Gradio应用对象
    return demo


def run_gradio_app():
    """运行Gradio应用"""
    demo = create_gradio_app()
    demo.launch(share=True, debug=True, queue=True)


if __name__ == "__main__":
    pass

    # gradio app还没有跑通
    # run_gradio_app()
