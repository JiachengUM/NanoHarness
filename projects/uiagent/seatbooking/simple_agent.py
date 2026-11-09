import os
from pathlib import Path
import re
from typing import Any, Dict, Optional

from PIL import Image
from jinja2 import Template
from pydantic import BaseModel, Field

from projects.uiagent.model.uitars import a_uitars_call, create_async_client
from projects.uiagent.prompts.uiagent_prompts import ACTION_SETS, FORMAT_INSTRUCTION
from projects.uiagent.seatbooking.prompts.seatbooking_prompts import (
    BOOKING_DETAIL_MISSON_DISCRIPTION,
    CONFIRM_SEAT_BOOKING_PERSON_INFO_PROMPT,
    RESTAURANT_BOOKING_PLAN,
    SEARCHING_RESTAURANT_SPECIFIC_MISSON_DISCRIPTION,
    TRY_TO_CLICK_SEAT_BOOKING_NODE_DISCRIPTION,
)
from projects.uiagent.utils.utils import a_download_url_image_to_memory, draw_actions, parse_action


class ActionInfo(BaseModel):
    reflection: Optional[Any] = Field(default=None, description="反思内容")
    thought: str = Field(description="思考过程")
    action_type: str = Field(description="操作类型")
    action_inputs: Dict[str, Any] = Field(description="操作输入参数，结构可变")
    text: str = Field(description="模型原始输出")


class SimpleInputRequest(BaseModel):
    image_cache_path: str = Field(description="图像缓存路径")
    trace_id: str | int | None = Field(default=None, description="唯一标识一次会话的ID")
    query: str = Field(description="query")
    view_image_url: str = Field(description="当前视野图片url")
    step: str | None = Field(default=None, description="输入图片所处业务步骤数")


class SimpleOutputResponse(BaseModel):
    trace_id: str | int | None = Field(default=None, description="唯一标识一次会话的ID")
    step: str | None = Field(default=None, description="输入图片所处业务步骤数")
    action_info: ActionInfo = Field(description="动作信息")
    query: str = Field(description="query")
    model_input_prompt: str = Field(description="模型输入prompt")
    cache_dir_path_with_file: str = Field(description="缓存渲染图像路径")
    drawed_in_memory_image: Any = Field(description="渲染后的内存内图像base64编码")
    image_type: str = Field(description="渲染后的图像类型")


SIMPLE_UI_AGENT_PROMPT = Template(
    """
你是一个非常强大的且擅长操作UI界面的专家，并且非常擅长与用户进行交流并尝试使用各种操作动作来解决用户的问题。
在这个过程中，你必须仔细阅读下述各种信息以及最后提供给你的当前视野图像进行合理的综合分析与决策来完成用户希望完成的任务。

首先你可以尝试的所有可选动作需从如下动作集合当中选择：

    ## 动作集合
    {{ action_sets }}

再是以下为整个美团订座的任务规划：
{{ restaurant_booking_plan }}

以下是用户的一个问题：
{{ query }}

综合以上信息以及同时参照着最后提供给你的当前视野图像后，你需要时刻牢记当下你需要使用动作在当前阶段完成以下任务：
{{ specific_misson_discription }}

你需要严格按照下面的要求进行回复。

{{ format_instruction }}

开始回复！
"""
)


def render_simple_mission_prompt(specific_misson_discription, query):
    """
    根据反思内容、上一步信息和背景信息渲染确认订座信息提示模板

    参数:
    query: 用户问题

    返回:
    渲染后的确认订座信息提示文本
    """
    return SIMPLE_UI_AGENT_PROMPT.render(
        action_sets=ACTION_SETS,
        restaurant_booking_plan=RESTAURANT_BOOKING_PLAN,
        query=query,
        format_instruction=FORMAT_INSTRUCTION,
        specific_misson_discription=specific_misson_discription,
    )


SIMPLE_REFLECT_PROMPT = Template(
    """
你是一个非常强大的且擅长操作UI界面的专家，并且非常擅长与用户进行交流并尝试使用各种操作动作来解决用户的问题。
而现在，有另外一个和你一样强的专家，使用如下一系列信息，得出了一个接下来应该执行的动作，并且你可以在最后一个视野图像，图像里的绿色点代表这个动作执行的位置。

首先你可以尝试的所有可选动作需从如下动作集合当中选择：

    ## 动作集合
    {{ action_sets }}

再是以下为整个美团订座的任务规划：
{{ restaurant_booking_plan }}

以下是用户的一个问题：
{{ query }}

另一个专家给出的下一个动作的信息：
{{ action_info }}

综合以上信息以及同时参照着最后提供给你的当前视野图像后，你需要时刻牢记当下你需要使用动作在当前阶段完成以下任务：
{{ specific_misson_discription }}

你需要根据以上信息，结合最后根据另一个专家给出的下一个动作渲染的视野图像，分析另一个专家给出的下一个动作是否是正确的。
如果不是正确的，你需要给出修正的意见。

你必须按照以下格式进行回复：

你必须严格按照以下三重反引号（```）内的格式回复：
    ```
    Correction: right or wrong
    Advice: $你的修正建议
    ```

同时你必须严格按照以下注意事项进行分析和回复：
    ## 注意事项
    - 在`Correction`部分，你只能回复`right`或者`wrong`；
    - 如果Correction是`right`，则Advice为None；
    - 如果Correction是`wrong`，则Advice必须包含修正建议，建议必须是中文，在建议中详细说明为什么是错误的以及应该如何修正；
    - 不要在回复中弄进来三重反引号（```）本身！
    - 如果要输入某个信息，那么得先点击输入框再输入；
"""
)


def render_simple_reflect_prompt(action_info, query, specific_misson_discription):
    """
    根据反思内容、上一步信息和背景信息渲染反思提示模板

    参数:
    action_info: 另一个专家给出的下一个动作的信息
    previous_info: 上一步信息
    back_ground_info: 背景信息

    返回:
    渲染后的反思提示文本
    """
    return SIMPLE_REFLECT_PROMPT.render(
        action_sets=ACTION_SETS,
        restaurant_booking_plan=RESTAURANT_BOOKING_PLAN,
        specific_misson_discription=specific_misson_discription,
        action_info=action_info,
        query=query,
    )


def pars_reflect_output(content_to_parse: str) -> tuple[str, str | None]:
    """
    解析反思输出，提取反思结果和建议
    """
    # 使用正则提取 Correction，支持中文全角冒号
    correction_match = re.search(
        r"Correction[：:]\s*(right|wrong)", content_to_parse, re.IGNORECASE
    )
    if not correction_match:
        raise ValueError(
            "解析失败：未找到有效的 Correction 字段，必须为 'right' 或 'wrong'"
        )
    correction = correction_match.group(1).lower()

    advice = None
    if correction == "wrong":
        # 支持中文全角冒号，并尽可能贪婪地捕获 Advice 内容直到字符串末尾
        advice_match = re.search(
            r"Advice[：:]\s*(.*)", content_to_parse, re.IGNORECASE | re.DOTALL
        )
        if not advice_match or not advice_match.group(1).strip():
            raise ValueError(
                "解析失败：Correction 为 'wrong' 时未找到有效的 Advice 字段"
            )
        advice = advice_match.group(1).strip()
    elif correction == "right":
        advice = None
    else:
        raise ValueError("解析失败：Correction 字段值无效，必须为 'right' 或 'wrong'")

    return correction, advice


class SimpleAgent:
    def __init__(self, image_cache_path: str):
        # self.ui_tars_client = create_langchain_client()
        self.ui_tars_client = create_async_client()
        self.image_cache_path = Path(image_cache_path)

    async def a_reflect(self, agent_output: SimpleOutputResponse) -> tuple[str, str]:
        # 动作信息提取出来成字符串
        action_info_string = (
            "action_type: "
            + agent_output.action_info.action_type
            + "\n"
            + "action_inputs: "
            + str(agent_output.action_info.action_inputs)
        )
        # 填充反思提示
        # 根据数据集case的step来确定使用哪个任务描述来处理step对应的任务画面
        if agent_output.step == "4":
            specific_misson_discription = CONFIRM_SEAT_BOOKING_PERSON_INFO_PROMPT
        elif agent_output.step == "3":
            specific_misson_discription = BOOKING_DETAIL_MISSON_DISCRIPTION
        elif agent_output.step == "1":
            specific_misson_discription = (
                SEARCHING_RESTAURANT_SPECIFIC_MISSON_DISCRIPTION
            )
        elif agent_output.step == "2":
            specific_misson_discription = TRY_TO_CLICK_SEAT_BOOKING_NODE_DISCRIPTION
        else:
            raise ValueError("step not in [1, 2, 3, 4]")
        reflect_prompt = render_simple_reflect_prompt(
            action_info=action_info_string,
            query=agent_output.query,
            specific_misson_discription=specific_misson_discription,
        )

        image_type = agent_output.image_type
        print(" ui tars reflecting...")
        response = await a_uitars_call(
            client=self.ui_tars_client,
            image=agent_output.cache_dir_path_with_file,
            image_type=image_type,
            prompt_type="custom_prompt",
            custom_prompt=reflect_prompt,
        )
        try:
            reflect_result, reflect_advice = pars_reflect_output(
                content_to_parse=response.content
            )
        except ValueError as e:
            raise ValueError(
                f"reflect output parse failed. content: {response.content}. error: {e}"
            )

        return reflect_result, reflect_advice

    async def a_action_decide(
        self, simple_input: SimpleInputRequest
    ) -> SimpleOutputResponse:
        # 根据数据集case的step来确定使用哪个任务描述来处理step对应的任务画面
        if simple_input.step == "4":
            specific_misson_discription = CONFIRM_SEAT_BOOKING_PERSON_INFO_PROMPT
        elif simple_input.step == "3":
            specific_misson_discription = BOOKING_DETAIL_MISSON_DISCRIPTION
        elif simple_input.step == "1":
            specific_misson_discription = (
                SEARCHING_RESTAURANT_SPECIFIC_MISSON_DISCRIPTION
            )
        elif simple_input.step == "2":
            specific_misson_discription = TRY_TO_CLICK_SEAT_BOOKING_NODE_DISCRIPTION
        else:
            raise ValueError("step not in [1, 2, 3, 4]")
        prompt = render_simple_mission_prompt(
            specific_misson_discription=specific_misson_discription,
            query=simple_input.query,
        )
        # 下载图片到内存里
        print("downloading image from " + simple_input.view_image_url)
        image_memory = await a_download_url_image_to_memory(simple_input.view_image_url)
        if image_memory is None:
            raise ValueError(
                f"download image from {simple_input.view_image_url} failed."
            )
        # image_type = Path(simple_input.view_image_url).suffix[1:]
        pil_image = Image.open(image_memory)
        image_type = pil_image.format.lower()
        cache_image_file_name = str(simple_input.trace_id) + "." + image_type
        cache_dir_path_with_file = os.path.join(
            self.image_cache_path, cache_image_file_name
        )
        # 获取模型原始输出
        print(" ui tars reasoning...")
        response = await a_uitars_call(
            client=self.ui_tars_client,
            image=image_memory,
            image_type=image_type,
            prompt_type="custom_prompt",
            custom_prompt=prompt,
        )
        # 把动作信息结构化解析出来
        try:
            parsed_action_list = parse_action(
                image=image_memory, content_to_parse=response.content
            )
        except:
            raise ValueError(f"parse action failed. content: {response.content}")
        action_info = ActionInfo(**parsed_action_list[0])
        # 渲染动作到图片上
        drawed_image = draw_actions(
            image=image_memory,
            output_path=cache_dir_path_with_file,
            parsed_actions_list=[action_info],
        )
        # 输出结果
        # drawed_image_base64 = encode_image(drawed_image)
        simple_output_response = SimpleOutputResponse(
            trace_id=simple_input.trace_id,
            step=simple_input.step,
            action_info=action_info,
            query=simple_input.query,
            model_input_prompt=prompt,
            cache_dir_path_with_file=cache_dir_path_with_file,
            drawed_in_memory_image=drawed_image,
            image_type=image_type,
        )
        return simple_output_response
