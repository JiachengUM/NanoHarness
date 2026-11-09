from jinja2 import Template

ACTION_SETS = """
click(point='<point>x1 y1</point>') # x1 y1分别为1-1000的整数，代表点击坐标点(x1 y1)。其他动作同理。
type(content='') # 如果你想提交你的输入文字，那么请务必在content内容的末尾加上"\\n"。
scroll(point='<point>x1 y1</point>', direction='down or up or right or left') #务必先判断现在可滑动的范围，从而判断能否向哪个方向滑动。
open_app(app_name='美团')
ask_human(content='请问你需要订几个人的座位？') # content是你需要反问人类的问题
finished(content='xxx') # 必须在内容中使用转义字符如\\'， \\"， 和 \\n等，以确保可以顺利解析成Python字符串。
"""

FORMAT_INSTRUCTION = """你必须严格按照以下三重反引号（```）内的格式回复：
    ```
    Thought: ...
    Action: 动作
    ```

同时你必须严格按照以下注意事项回复！！否则干死你！！：
    ## 注意事项
    - 在`Thought`部分使用中文；
    - 在`Thought`部分，你先对照整个美团订座的任务规划，根据“在之前一步规划中进行的下一步思考”的信息,以及最后的当前视野下图像，判断当前任务执行状态处于哪一个过程中，然后决定下一步行动应该采取哪种行动。
    - 确保一次只进行一个动作；
    - 默认或者选中状态的不需要再去点击；
    - 动作的坐标里不要用逗号，用空格隔开；
    - 不要在回复中弄进来三重反引号（```）本身！"""

UI_AGENT_PROMPT = Template(
    """
你是一个非常强大的且擅长操作UI界面的专家，并且非常擅长与用户进行交流并尝试使用各种操作动作来解决用户的问题。
在这个过程中，你必须仔细阅读下述各种信息以及最后提供给你的当前视野图像进行合理的综合分析与决策来完成用户希望完成的任务。

首先你可以尝试的所有可选动作需从如下动作集合当中选择：

    ## 动作集合
    {{ action_sets }}

{% if back_ground_info %}
其次以下有一些背景信息很可能你可以用到：
{{ back_ground_info }}
{% endif %}

再是以下为整个美团订座的任务规划：
{{ restaurant_booking_plan }}

{% if previous_info %}
以下是“在之前一步规划中进行的下一步思考”，而你需要仔细阅读以下信息并对照着任务规划来判断当前任务执行状态，思考并决策接下来采取的动作：
{{ previous_info }}
{% endif %}

{% if reflection %}
此外，以下是一些对你上次的动作决策进行观察分析并进行反思后得出的一些建议，可供你参考得出更合理的决策：
{{ reflection }}
{% endif %}

{% if history %}
最后，以下是你和用户的对话记录：
{{ history }}
{% endif %}

综合以上信息以及同时参照着最后提供给你的当前视野图像后，你需要时刻牢记当下你需要使用动作在当前阶段完成以下任务：
{{ specific_misson_discription }}

你需要严格按照下面的要求进行回复。

{{ format_instruction }}

开始回复！
"""
)


def render_mission_prompt(
    plan,
    specific_misson_discription,
    reflection=None,
    previous_info=None,
    back_ground_info=None,
    history=None,
):
    """
    根据反思内容、上一步信息和背景信息渲染确认订座信息提示模板

    参数:
    plan: 任务规划
    specific_misson_discription: 任务描述
    reflection: 反思内容
    previous_info: 上一步信息
    back_ground_info: 背景信息

    返回:
    渲染后的确认订座信息提示文本
    """
    return UI_AGENT_PROMPT.render(
        action_sets=ACTION_SETS,
        restaurant_booking_plan=plan,
        reflection=reflection,
        previous_info=previous_info,
        back_ground_info=back_ground_info,
        history=history,
        format_instruction=FORMAT_INSTRUCTION,
        specific_misson_discription=specific_misson_discription,
    )


REFLECT_PROMPT = Template(
    """
你是一个非常强大的且擅长操作UI界面的专家，并且非常擅长与用户进行交流并尝试使用各种操作动作来解决用户的问题。
而现在，有另外一个和你一样强的专家，使用如下一系列信息，得出了一个接下来应该执行的动作，并且你可以在最后一个视野图像，图像里的绿色点代表这个动作执行的位置。

首先你可以尝试的所有可选动作需从如下动作集合当中选择：

    ## 动作集合
    {{ action_sets }}

{% if back_ground_info %}
其次以下有一些背景信息很可能你可以用到：
{{ back_ground_info }}
{% endif %}

再是以下为整个美团订座的任务规划：
{{ restaurant_booking_plan }}

{% if previous_info %}
以下是“在之前一步规划中进行的下一步思考”，而你需要仔细阅读以下信息并对照着任务规划来判断当前任务执行状态，思考并决策接下来采取的动作：
{{ previous_info }}
{% endif %}

另一个专家给出的下一个动作的信息：
{{ action_info }}

综合以上信息以及同时参照着最后提供给你的当前视野图像后，你需要时刻牢记当下你需要使用动作在当前阶段完成以下任务：
{{ specific_misson_discription }}

{% if history %}
最后，以下是你和用户的对话记录：
{{ history }}
{% endif %}

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


def render_reflect_prompt(
    action_info,
    previous_info,
    plan,
    specific_misson_discription,
    back_ground_info=None,
    history=None,
):
    """
    根据反思内容、上一步信息和背景信息渲染反思提示模板

    参数:
    action_info: 另一个专家给出的下一个动作的信息
    previous_info: 上一步信息
    back_ground_info: 背景信息

    返回:
    渲染后的反思提示文本
    """
    return REFLECT_PROMPT.render(
        action_sets=ACTION_SETS,
        restaurant_booking_plan=plan,
        specific_misson_discription=specific_misson_discription,
        action_info=action_info,
        previous_info=previous_info,
        back_ground_info=back_ground_info,
        history=history,
    )


ROUTE_NODE_PROMPT = f"""
你是一个非常擅长图像理解的专家。

根据之后的视野图像，判断当前页面处于下述哪个业务流程名称的集合中的哪个业务流程中，并且从“业务流程名称的集合”中选择一个
业务流程名称作为回复。

“业务流程名称的集合”：{{stages}}

你必须严格按照以下三重反引号（```）内的格式回复：
```
Stage: $业务流程名称
```

## 记住！！
- 你回复的业务流程名称必须是选择自“业务流程名称的集合”中的一个！！
- 不要给出其他多余信息。
- 不要在回复中弄进来三重反引号（```）本身！
- 绝对不要回复任何不在“业务流程名称的集合”中的业务流程名称！
"""
