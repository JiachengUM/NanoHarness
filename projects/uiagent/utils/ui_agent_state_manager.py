from typing import List, Optional, Union
from openai.types.chat import ChatCompletionMessageParam
import json
from pydantic import BaseModel, Field
from projects.uiagent.server.utils.redis_util import RedisUtil

class UIAgentState(BaseModel):
    """
    智能体状态
    """
    history: List[ChatCompletionMessageParam] = Field(title="智能体上下文", description="智能体上下文")
    next_step: str = Field(title="下一步task", description="智能体下一步task")

class UIAgentStateManager:
    """
    智能体状态管理工具
    支持：1.按轮次保留上下文 2.控制带图片上下文保留轮数 3.是否保留第一个对话信息，4.保存智能体状态
    """

    def __init__(
            self,
            max_rounds: Optional[int] = None,
            max_image_contexts: Optional[int] = None,
            keep_first_message: bool = False,  # 是否保留第一个对话信息
            chat_id: Optional[str] = "",
            expire_seconds: Optional[int] = 3600,
            redis_client: Optional[RedisUtil] = None,
    ):
        """
        初始化上下文管理器

        Args:
            max_rounds: 最大保留轮数（None表示全部保留）
                        注：一轮对话指一个用户消息 + 一个助手回复（如果存在）
            max_image_contexts: 带图片上下文的最大保留轮数（None表示全部保留）
            keep_first_message: 是否保留第一个对话信息（无论轮次过滤如何，始终保留初始消息）
            chat_id: 智能体会话Id
            scene: 场景,一个智能体中可能会调用多个大模型，分场景存储各自上下文
            redis_client: redis客户端
        """
        self.max_rounds = max_rounds
        self.max_image_contexts = max_image_contexts
        self.keep_first_message = keep_first_message
        self.chat_id = chat_id
        self.expire_seconds = expire_seconds
        self.redis_client = redis_client
        self._context: List[ChatCompletionMessageParam] = []
        self._first_message: Optional[ChatCompletionMessageParam] = None  # 存储第一个消息

    def _contains_image(self, message: ChatCompletionMessageParam) -> bool:
        """判断单条消息是否包含图片内容"""
        content = message.get("content")
        if not content:
            return False

        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "image_url":
                    return True

        return False

    def _group_by_rounds(self, messages: List[ChatCompletionMessageParam]) -> List[List[ChatCompletionMessageParam]]:
        """将消息按轮次分组（用户消息 + 助手回复为一轮）"""
        rounds: List[List[ChatCompletionMessageParam]] = []
        current_round: List[ChatCompletionMessageParam] = []

        for msg in messages:
            role = msg.get("role")

            if role == "user" and current_round:
                rounds.append(current_round)
                current_round = [msg]
            else:
                current_round.append(msg)

        if current_round:
            rounds.append(current_round)

        return rounds

    def update_context(self, new_messages: List[ChatCompletionMessageParam]) -> List[ChatCompletionMessageParam]:
        """
        更新上下文并返回处理后的结果

        Args:
            new_messages: 新的消息列表（完整的上下文历史）

        Returns:
            处理后的上下文列表
        """
        # 保存完整上下文
        self._context = new_messages.copy()

        # 记录第一个消息（如果存在且需要保留）
        self._first_message = new_messages[0] if new_messages and self.keep_first_message else None

        # 1. 按轮次分组
        message_rounds = self._group_by_rounds(self._context)

        # 2. 处理带图片的上下文保留逻辑
        filtered_rounds = self._filter_image_contexts(message_rounds)

        # 3. 处理总轮次保留逻辑
        final_rounds = self._filter_by_max_rounds(filtered_rounds)

        # 4. 展平轮次列表
        final_context = [msg for round_msgs in final_rounds for msg in round_msgs]

        # 5. 如果需要保留第一个消息，确保它在最终上下文的最前面
        if self._first_message and final_context:
            # 检查第一个消息是否已经在最终上下文中（避免重复）
            first_msg_exists = any(
                msg.get("role") == self._first_message.get("role")
                and msg.get("content") == self._first_message.get("content")
                for msg in final_context
            )
            if not first_msg_exists:
                final_context.insert(0, self._first_message)
        elif self._first_message and not final_context:
            # 极端情况：过滤后没有其他消息，只保留第一个消息
            final_context = [self._first_message]

        return final_context

    def _filter_image_contexts(self, rounds: List[List[ChatCompletionMessageParam]]) -> List[
        List[ChatCompletionMessageParam]]:
        """过滤带图片的上下文，保留指定轮数"""
        if self.max_image_contexts is None:
            return rounds

        # 收集包含图片的轮次索引
        image_round_indices = []
        for idx, round_msgs in enumerate(rounds):
            if any(self._contains_image(msg) for msg in round_msgs):
                image_round_indices.append(idx)

        # 需要保留的带图片轮次（最新的N轮）
        keep_image_indices = set(
            image_round_indices[-self.max_image_contexts:]
            if len(image_round_indices) >= self.max_image_contexts
            else image_round_indices
        )

        # 过滤轮次：保留非图片轮次 + 需要保留的图片轮次
        filtered = []
        for idx, round_msgs in enumerate(rounds):
            has_image = any(self._contains_image(msg) for msg in round_msgs)
            if not has_image or idx in keep_image_indices:
                filtered.append(round_msgs)

        return filtered

    def _filter_by_max_rounds(self, rounds: List[List[ChatCompletionMessageParam]]) -> List[
        List[ChatCompletionMessageParam]]:
        """按最大轮次限制过滤上下文"""
        if self.max_rounds is None or self.max_rounds <= 0:
            return rounds

        # 保留最新的N轮
        return rounds[-self.max_rounds:] if len(rounds) > self.max_rounds else rounds

    def get_current_context(self) -> List[ChatCompletionMessageParam]:
        """获取当前处理后的上下文"""
        return self._context.copy()

    def get_first_message(self) -> Optional[ChatCompletionMessageParam]:
        """获取第一个对话信息（如果已保留）"""
        return self._first_message.copy() if self._first_message else None

    def save_message(self, messages: List[ChatCompletionMessageParam], next_step: str) -> None:
        """保存新的消息到上下文"""
        messages = self.update_context(messages)
        ui_agent_state = UIAgentState(history=messages, next_step=next_step)
        s = ui_agent_state.model_dump_json(exclude_none=True)
        key = f"gui#{self.chat_id}"
        self.redis_client.set(key, s, self.expire_seconds)

    def get_messages(self) -> UIAgentState:
        """从Redis获取上下文"""
        s = self.redis_client.get(f"gui#{self.chat_id}")
        state = UIAgentState.model_validate_json(s)
        return state



# ------------------------------
# 使用示例
# ------------------------------
# 构建测试上下文（包含文本和图片消息）
test_context1: List[ChatCompletionMessageParam] = [
        # 第1轮：纯文本
        {
            "role": "user",
            "content": "你是一个强大的手机手机操作者。在最后你总会看到一个你看到的当前视野的图像。你需要仔细阅读以下信息，做出正确的动作信息决策，以便在页面上执行相应的动作来完成用户任务。以下是详细描述：\n应用程序当前页面描述: 选择车辆页面\n动作空间: \n1. click(point='<point>x1 y1</point>')\n2. type(content='')\n3. scroll(point='<point>x1 y1</point>', direction='down or up or right or left')\n4. ask_human(content='')\n任务描述: 帮我缴一下停车费\n注意事项: \n1. 如果你在当前页面上没有看到任何车辆信息，并且看到让你添加车辆，输车牌缴费，那么点击输车牌缴费；\n2. 如果你看到当前页面左上角直接有车牌信息，那么首先和背景信息里的用户车牌号对比，确认是否是当前用户的车辆，如果不是，那么直接点击左上角的车牌号；\n3. 如果你看到当前页面在左上角弹出了一个小弹窗，里面有一个或多个车牌信息，以及其他车辆和绑定车辆选项，那么首先比对确认是否存在当前用户的车辆牌照号，如果有，那么直接点击之，如果没有，那么点击其他车辆选项；\n4. 当你看到并最终确认当前页面左上角无弹窗且直接有一个和用户车牌号相同的车牌号时，那么你会看到当前用户车辆的在该停车场的订单状况，根据不同情况进行下一步点击查看订单明细（注意，不要点查订单那个小按钮）或金额确认的点击操作，或者如果是无需缴费的情况，直接用finished动作结束任务并在其content里告诉用户你可以直接开出去了因为你是月卡用户或者时间短无需缴费或者人工缴费等；\n5. 接上条，而如果是当前用户希望缴费的车辆不存在订单的情况，先尝试点击一次刷新订单操作，如果在一次刷新订单操作后依然没有订单信息，那么询问用户告诉他当前希望缴费的车辆查不到其订单，是否希望给其他车辆缴费，如果之后用户不希望给其他车辆缴费那么直接finished结束任务；\n6. 如果你看到页面上显示在加载中，那么点击一下页面的空白处，看看过会儿是否加载完成；\n7. 如果用户让你帮他给一个具体的与背景信息里用户车牌号不同的车牌号缴费，那么当前你需要选择的缴费车辆以用户告诉你的为准；\n\n\n请按照以下格式回复\n\nThought: ...\nAction: ...\n\n同时你必须严格按照以下注意事项回复！！否则干死你！！：\n    ## 注意事项\n    - 在`Thought`部分使用中文；\n    - 你需要仔细阅读上文中的任务描述以及动作空间，结合下面的当前视野图像，写出你对当前状况的思考以及判断以及接下来一步动作你应该做什么；\n    - 确保Action后面的动作只引用动作空间中的动作；\n    - 确保一次只进行一个动作；\n    - 默认或者选中状态的不需要再去点击；\n    - 动作的坐标里不要用逗号，用空格隔开；\n    - 严格按照动作空间里动作的格式回复！特别是ask_human或finished动作，你必须严格按照`ask_human(content='回复的内容')`或`finished(content='回复的内容')`格式回复！\n\n"
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": "https://example.com/image1.jpg"
                    }
                }
            ]
        },
        {
            "role": "assistant",
            "content": "点击第一个按钮"
        },
        # 第2轮：带图片
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": "这张图片里是什么？"
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": "https://example.com/image1.jpg"
                    }
                }
            ]
        },
        {
            "role": "assistant",
            "content": "这是一张风景图片"
        },
        # 第3轮：带图片
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": "https://example.com/image2.jpg"
                    }
                }
            ]
        },
        {
            "role": "assistant",
            "content": "这是一只猫的图片"
        },
        # 第4轮：纯文本
        {
            "role": "user",
            "content": "谢谢解答"
        },
        {
            "role": "assistant",
            "content": "不客气！有其他问题可以随时问我"
        }
    ]
test_context2: List[ChatCompletionMessageParam] = [
        # 第1轮
        {
            "role": "user",
            "content": "你是一个强大的手机手机操作者。在最后你总会看到一个你看到的当前视野的图像。你需要仔细阅读以下信息，做出正确的动作信息决策，以便在页面上执行相应的动作来完成用户任务。以下是详细描述：\n应用程序当前页面描述: 选择车辆页面\n动作空间: \n1. click(point='<point>x1 y1</point>')\n2. type(content='')\n3. scroll(point='<point>x1 y1</point>', direction='down or up or right or left')\n4. ask_human(content='')\n任务描述: 帮我缴一下停车费\n注意事项: \n1. 如果你在当前页面上没有看到任何车辆信息，并且看到让你添加车辆，输车牌缴费，那么点击输车牌缴费；\n2. 如果你看到当前页面左上角直接有车牌信息，那么首先和背景信息里的用户车牌号对比，确认是否是当前用户的车辆，如果不是，那么直接点击左上角的车牌号；\n3. 如果你看到当前页面在左上角弹出了一个小弹窗，里面有一个或多个车牌信息，以及其他车辆和绑定车辆选项，那么首先比对确认是否存在当前用户的车辆牌照号，如果有，那么直接点击之，如果没有，那么点击其他车辆选项；\n4. 当你看到并最终确认当前页面左上角无弹窗且直接有一个和用户车牌号相同的车牌号时，那么你会看到当前用户车辆的在该停车场的订单状况，根据不同情况进行下一步点击查看订单明细（注意，不要点查订单那个小按钮）或金额确认的点击操作，或者如果是无需缴费的情况，直接用finished动作结束任务并在其content里告诉用户你可以直接开出去了因为你是月卡用户或者时间短无需缴费或者人工缴费等；\n5. 接上条，而如果是当前用户希望缴费的车辆不存在订单的情况，先尝试点击一次刷新订单操作，如果在一次刷新订单操作后依然没有订单信息，那么询问用户告诉他当前希望缴费的车辆查不到其订单，是否希望给其他车辆缴费，如果之后用户不希望给其他车辆缴费那么直接finished结束任务；\n6. 如果你看到页面上显示在加载中，那么点击一下页面的空白处，看看过会儿是否加载完成；\n7. 如果用户让你帮他给一个具体的与背景信息里用户车牌号不同的车牌号缴费，那么当前你需要选择的缴费车辆以用户告诉你的为准；\n\n\n请按照以下格式回复\n\nThought: ...\nAction: ...\n\n同时你必须严格按照以下注意事项回复！！否则干死你！！：\n    ## 注意事项\n    - 在`Thought`部分使用中文；\n    - 你需要仔细阅读上文中的任务描述以及动作空间，结合下面的当前视野图像，写出你对当前状况的思考以及判断以及接下来一步动作你应该做什么；\n    - 确保Action后面的动作只引用动作空间中的动作；\n    - 确保一次只进行一个动作；\n    - 默认或者选中状态的不需要再去点击；\n    - 动作的坐标里不要用逗号，用空格隔开；\n    - 严格按照动作空间里动作的格式回复！特别是ask_human或finished动作，你必须严格按照`ask_human(content='回复的内容')`或`finished(content='回复的内容')`格式回复！\n\n"
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": "https://example.com/image1.jpg"
                    }
                }
            ]
        },
        {
            "role": "assistant",
            "content": "点击第一个按钮"
        },
        # 第2轮
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": "https://example.com/image2.jpg"
                    }
                }
            ]
        },
        {
            "role": "assistant",
            "content": "点击第2个按钮"
        },
        # 第3轮
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": "https://example.com/image3.jpg"
                    }
                }
            ]
        },
        {
            "role": "assistant",
            "content": "点击第3个按钮"
        },
        # 第4轮
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": "https://example.com/image4.jpg"
                    }
                }
            ]
        },
        {
            "role": "assistant",
            "content": "点击第4个按钮"
        },
		# 第5轮
		{
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": "https://example.com/image5.jpg"
                    }
                }
            ]
        },
        {
            "role": "assistant",
            "content": "点击第5个按钮"
        }
    ]
def run1():
    # 示例1：保留最新2轮，最多保留1轮带图片的上下文
    print("=== 示例1：max_rounds=2, max_image_contexts=1 ===")
    manager1 = UIAgentStateManager(max_rounds=2, max_image_contexts=1, keep_first_message=False)
    result1 = manager1.update_context(test_context1)
    print(json.dumps(result1, ensure_ascii=False, indent=2))


def run2():
    # 示例2：保留全部轮次，最多保留1轮带图片的上下文
    print("=== 示例2：max_rounds=None, max_image_contexts=1 ===")
    manager2 = UIAgentStateManager(max_rounds=None, max_image_contexts=1)
    result2 = manager2.update_context(test_context1)
    print(json.dumps(result2, ensure_ascii=False, indent=2))


def run3():
    print("=== 示例3：max_rounds=1, max_image_contexts=None ===")
    manager3 = UIAgentStateManager(max_rounds=None, max_image_contexts=2, keep_first_message=True)
    result3 = manager3.update_context(test_context2)
    print(json.dumps(result3, ensure_ascii=False, indent=2))

def save_message():
    redis_client = RedisUtil(
        host='r-bp1phz2qws21z63xvmpd.redis.rds.aliyuncs.com',
        port=6379,
        db=4,
        password='REDACTED',  # 无密码则设为 None
        decode_responses=True
    )
    manager = UIAgentStateManager(
        max_rounds=None,
        max_image_contexts=2,
        keep_first_message=True,
        chat_id="1002",
        expire_seconds=1000,
        redis_client=redis_client
    )
    manager.save_message(test_context2, "zzz")

def get_message():
    redis_client = RedisUtil(
        host='r-bp1phz2qws21z63xvmpd.redis.rds.aliyuncs.com',
        port=6379,
        db=4,
        password='REDACTED',  # 无密码则设为 None
        decode_responses=True
    )
    manager = UIAgentStateManager(
        max_rounds=None,
        max_image_contexts=2,
        keep_first_message=True,
        chat_id="1002",
        expire_seconds=1000,
        redis_client=redis_client
    )
    res = manager.get_messages()
    print(res.next_step)
if __name__ == "__main__":
    save_message()
    get_message()