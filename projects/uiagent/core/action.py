from enum import StrEnum
import re

from pydantic import BaseModel, Field
from ui_tars.action_parser import ast_parse, escape_single_quotes
from typing import Any, Type
import copy


class UiElement(BaseModel):
    """一个UI元素的信息描述。这个元素可能成为各种各样动作的目标。可被继承并扩展至各种具体的目标类型如按钮，输入栏，选项框等。
    这个目标主要用于加入Page当中，给大模型描述一些与业务处理息息相关的页面元素以便大模型能够充分理解并在一些动作当中输出它的动作目标供后续ui_task使用。"""
    name: str = Field(description="目标名称")
    description: str = Field(description="目标描述")


class Button(UiElement):
    """继承自UiElement，表示一个UI按钮的信息描述。每一个具体的按钮都应该是这个类的一个实例，并且一定要好好写这个按钮的名称与app上对齐或者自己好好命名！
    描述当中一定要好好描述这个按钮的功能与作用，例如“确认订单”、“提交表单”等。"""
    name: str = Field(description="按钮名称")
    description: str = Field(description="按钮描述")


class InputBox(UiElement):
    """继承自UiElement，表示一个UI输入栏的信息描述。每一个具体的输入栏都应该是这个类的一个实例，并且一定要好好写这个输入栏的名称与app上对齐或者自己好好命名！
    描述当中一定要好好描述这个输入栏的功能与作用，例如“请输入用户名”、“请输入密码”等。"""
    name: str = Field(description="输入栏名称")
    description: str = Field(description="输入栏功能描述")
    # 这玩意儿很重要，在有输入栏的app里，有可能你需要明确告诉大模型这个输入栏最多输入几个字，以便大模型按需生成合适的输入内容
    max_length: int = Field(description="输入栏最大可输入字符的长度")


class ActionType(StrEnum):
    CLICK = "click"
    TYPE = "type"
    SCROLL = "scroll"
    DRAG = "drag"
    WAIT = "wait"
    ASK = "ask_human"
    FINISHED = "finished"


class PointCoordinate(BaseModel):
    x: float = Field(
        title="x坐标", description="x坐标,0-1取值的浮点数相对坐标，精确到小数点后3位"
    )
    y: float = Field(
        title="y坐标", description="y坐标,0-1取值的浮点数相对坐标，精确到小数点后3位"
    )

# action的name是给前端用的，否则前端不知道这是什么动作。


class ClickAction(BaseModel):
    name: str = ActionType.CLICK.value
    x: float = Field(
        title="x坐标", description="x坐标,0-1取值的浮点数相对坐标，精确到小数点后3位"
    )
    y: float = Field(
        title="y坐标", description="y坐标,0-1取值的浮点数相对坐标，精确到小数点后3位"
    )
    target_ui_element: UiElement | None = Field(
        default=None, title="目标", description="点击的目标元素，可选。"
    )


class TypeAction(BaseModel):
    name: str = ActionType.TYPE.value
    content: str = Field(title="内容", description="内容")


class ScrollAction(BaseModel):
    name: str = ActionType.SCROLL.value
    x: float = Field(
        title="x坐标", description="x坐标,0-1取值的浮点数相对坐标，精确到小数点后3位"
    )
    y: float = Field(
        title="y坐标", description="y坐标,0-1取值的浮点数相对坐标，精确到小数点后3位"
    )
    dir: str = Field(title="方向", description="方向,可选值:down,up,right,left")


class DragAction(BaseModel):
    name: str = ActionType.DRAG.value
    x: float = Field(
        title="拖拽起点x坐标", description="拖拽起点x坐标,0-1取值的浮点数相对坐标，精确到小数点后3位"
    )
    y: float = Field(
        title="拖拽起点y坐标", description="拖拽起点y坐标,0-1取值的浮点数相对坐标，精确到小数点后3位"
    )
    end_point_x: float = Field(
        title="拖拽终点x坐标", description="拖拽终点x坐标,0-1取值的浮点数相对坐标，精确到小数点后3位"
    )
    end_point_y: float = Field(
        title="拖拽终点y坐标", description="拖拽终点y坐标,0-1取值的浮点数相对坐标，精确到小数点后3位"
    )
    target_ui_element: UiElement | None = Field(
        default=None, title="目标", description="拖动的目标元素，可选。"
    )


class AskAction(BaseModel):
    name: str = ActionType.ASK.value
    content: str = Field(title="智能体反问用户或向用户反馈的信息。", description="内容")


class WaitAction(BaseModel):
    name: str = ActionType.WAIT.value


class FinishedAction(BaseModel):
    name: str = ActionType.FINISHED.value
    content: str = Field(title="完成任务时需要反馈给用户的信息。", description="内容")


Action = ClickAction | TypeAction | ScrollAction | DragAction | AskAction | WaitAction | FinishedAction


def match_ui_element_in_page(raw_ui_element_name: str, ui_element_dict: dict[str, UiElement] | None) -> UiElement | None:
    """因为预计很多动作都需要从Page中匹配ui_element，所以这里单独抽出来这个函数"""
    if ui_element_dict:
        if raw_ui_element_name == "":
            ui_element = None
        else:
            if raw_ui_element_name not in ui_element_dict.keys():
                warning_message = f"Raw ui_element name: {raw_ui_element_name} not found in ui_element_dict keys: \n{ui_element_dict.keys()}."
                print(warning_message)
                # click的ui_element不一定要出现在Page里，Page里只会提到关乎工作流跳转的关键ui_elements。如果点击了一个不在Page里的ui_element，说明这个ui_element不重要，
                # 则认为是这不是业务关心的ui_element，直接创建一个新的ui_element对象，直接用提取出的名称来命名这个ui_element。
                if raw_ui_element_name:
                    ui_element = Button(
                        name=raw_ui_element_name, description=raw_ui_element_name)
                else:
                    ui_element = Button(name="一个未知按钮", description="一个未知按钮")
            else:
                ui_element = ui_element_dict[raw_ui_element_name]
            # 理论上暂定现在click的对象只能是Button，后续如果有需要，再考虑其他类型的可点击ui_element。
            assert isinstance(
                ui_element, (Button, InputBox)), f"ui_element {raw_ui_element_name} is not a Button or InputBox."
    else:   # 没传Page时，没法知道ui_element，所以置为None
        ui_element = None
    return ui_element


def parse_action(action_content: str, ui_element_dict: dict[str, UiElement] | None = None, factor: int = 1000) -> list[Action]:
    # 正则表达式匹配 content 中的字符串并转义单引号
    def escape_quotes(match):
        content = match.group(1)  # 获取 content 的值
        return content
    print("&"*100)
    print(action_content)
    print("&"*100)
    # 模型输出偶尔会出现换行数不同的情况，统一规范化分隔符为 )\n\n
    normalized_content = re.sub(r"\)\s*\n+", ")\n\n", action_content)
    tmp_all_action = normalized_content.split(")\n\n")
    all_action = []
    for action_str in tmp_all_action:
        if "type(content" in action_str:
            if not action_str.strip().endswith(")"):
                action_str = action_str.strip() + ")"

            # 使用正则表达式进行替换
            pattern = r"type\(content='(.*?)'\)"  # 匹配 type(content='...')
            if re.search(pattern, action_str):  # 检查是否有匹配项
                content = re.sub(pattern, escape_quotes, action_str)
            else:
                raise ValueError("Pattern not found in the input string.")

            # 处理字符串
            action_str = escape_single_quotes(content)
            action_str = "type(content='" + action_str + "')"
        # 增加 ask_human ,可以与type统一起来
        if "ask_human(content" in action_str:
            if not action_str.strip().endswith(")"):
                action_str = action_str.strip() + ")"

            # 使用正则表达式进行替换
            # 匹配 ask_human(content='...')
            pattern = r"ask_human\(content='(.*?)'\)"
            if re.search(pattern, action_str):  # 检查是否有匹配项
                content = re.sub(pattern, escape_quotes, action_str)
            else:
                raise ValueError("Pattern not found in the input string.")

            # 处理字符串
            action_str = escape_single_quotes(content)
            action_str = "ask_human(content='" + action_str + "')"

        # 增加 finished
        if "finished(content" in action_str:
            if not action_str.strip().endswith(")"):
                action_str = action_str.strip() + ")"

            # 使用正则表达式进行替换
            # 匹配 finished(content='...')
            pattern = r"finished\(content='(.*?)'\)"
            if re.search(pattern, action_str):  # 检查是否有匹配项
                content = re.sub(pattern, escape_quotes, action_str)
            else:
                raise ValueError("Pattern not found in the input string.")

            # 处理字符串
            action_str = escape_single_quotes(content)
            action_str = "finished(content='" + action_str + "')"

        if not action_str.strip().endswith(")"):
            action_str = action_str.strip() + ")"
        all_action.append(action_str)

    parsed_actions = [
        ast_parse(action.replace("\n", "\\n").lstrip()) for action in all_action
    ]
    actions: list[Action] = []
    for action_instance, raw_str in zip(parsed_actions, all_action):
        if action_instance == None:
            print(f"Action can't parse: {raw_str}")
            raise ValueError(f"Action can't parse: {raw_str}")
        action_type = action_instance["function"]
        params = action_instance["args"]

        action_inputs = {}
        for param_name, param in params.items():
            # if param == "":
            #     continue
            if isinstance(param, str):
                param = param.lstrip()  # 去掉引号和多余的空格
            # 处理start_box或者end_box参数格式 '<bbox>x1 y1 x2 y2</bbox>'
            action_inputs[param_name.strip()] = param

            if "start_box" in param_name or "end_box" in param_name:
                ori_box = param
                # Remove parentheses and split the string by commas
                numbers = ori_box.replace("(", "").replace(")", "").split(",")

                # Convert to float and scale by 1000
                try:
                    float_numbers = [float(num) / factor for num in numbers]
                    print("?"*100)
                    print(params)
                    print("?"*100)
                except Exception as e:
                    raise ValueError(
                        f"参数解析出错了，原始待解析参数字符串为: {params}。原始字符串为：{action_content}") from e

                if len(float_numbers) == 2:
                    float_numbers = [
                        float_numbers[0],
                        float_numbers[1],
                        float_numbers[0],
                        float_numbers[1],
                    ]
                elif len(float_numbers) == 4:
                    float_numbers = [
                        float_numbers[0],
                        float_numbers[1],
                        float_numbers[2],
                        float_numbers[3],
                    ]
                action_inputs[param_name.strip()] = float_numbers
    # import pdb; pdb.set_trace()
        if action_type == ActionType.SCROLL:
            actions.append(
                ScrollAction(
                    x=action_inputs["start_box"][0],
                    y=action_inputs["start_box"][1],
                    dir=action_inputs["direction"].lower(),
                )
            )
        elif action_type == ActionType.CLICK:
            # 在这里，取出原始的模型输出的ui_element name，尝试匹配到Page里的ui_elements
            ui_element = match_ui_element_in_page(
                action_inputs["target_ui_element"], ui_element_dict)
            actions.append(ClickAction( 
                x=action_inputs["start_box"][0],
                y=action_inputs["start_box"][1],
                target_ui_element=ui_element,
            ))
        elif action_type == ActionType.TYPE:
            actions.append(TypeAction(content=action_inputs["content"]))
        elif action_type == ActionType.DRAG:
            ui_element = match_ui_element_in_page(
                action_inputs["target_ui_element"], ui_element_dict)
            actions.append(
                DragAction(
                    x=action_inputs["start_box"][0],
                    y=action_inputs["start_box"][1],
                    end_point_x=action_inputs["end_box"][0],
                    end_point_y=action_inputs["end_box"][1],
                    target_ui_element=ui_element,
                )
            )
        elif action_type == ActionType.ASK:
            actions.append(AskAction(content=action_inputs["content"]))
        elif action_type == ActionType.WAIT:
            actions.append(WaitAction())
        elif action_type == ActionType.FINISHED:
            actions.append(FinishedAction(content=action_inputs["content"]))
    return actions


def norm_actions(actions: list[Action], width: int, height: int) -> list[Action]:
    new_actions = []
    for act in actions:
        if isinstance(act, (ClickAction, ScrollAction)):
            if act.x >= 1 or act.y >= 1:
                act.x = round(act.x / width, 3)
                act.y = round(act.y / height, 3)
        elif isinstance(act, DragAction):
            if act.x >= 1 or act.y >= 1:
                act.x = round(act.x / width, 3)
                act.y = round(act.y / height, 3)
            if act.end_point_x >= 1 or act.end_point_y >= 1:
                act.end_point_x = round(act.end_point_x / width, 3)
                act.end_point_y = round(act.end_point_y / height, 3)
        new_actions.append(act)

    return new_actions


def inline_refs(schema: dict[str, Any], defs: dict[str, Any]) -> dict[str, Any]:
    """
    递归展开 $ref（仅支持 #/$defs/xxx 这种 Pydantic 生成的引用）
    """
    if isinstance(schema, list):
        return [inline_refs(item, defs) for item in schema]

    if not isinstance(schema, dict):
        return schema

    # 命中 $ref
    if "$ref" in schema:
        ref = schema["$ref"]
        if ref.startswith("#/$defs/"):
            key = ref.split("/")[-1]
            if key not in defs:
                raise ValueError(f"Unresolved $ref: {ref}")

            resolved = copy.deepcopy(defs[key])

            # 合并 ref 外的额外字段（如 description）
            for k, v in schema.items():
                if k != "$ref":
                    resolved[k] = v

            return inline_refs(resolved, defs)

    # 普通递归
    return {
        k: inline_refs(v, defs)
        for k, v in schema.items()
        if k != "$defs"
    }

def force_no_additional_properties(schema: dict[str, Any]):
    if not isinstance(schema, dict):
        return

    if schema.get("type") == "object":
        schema.setdefault("additionalProperties", False)
        for prop in schema.get("properties", {}).values():
            force_no_additional_properties(prop)

    elif schema.get("type") == "array":
        force_no_additional_properties(schema.get("items"))

    for key in ("anyOf", "oneOf", "allOf"):
        if key in schema:
            for sub in schema[key]:
                force_no_additional_properties(sub)


def basemodel_to_openai_tool_schema(
    model: Type[BaseModel],
    *,
    name: str | None = None,
    description: str | None = None,
) -> dict[str, Any]:
    """
    BaseModel -> OpenAI tool_call schema

    """
    raw_schema = model.model_json_schema()

    defs = raw_schema.get("$defs", {})

    parameters = {
        "type": "object",
        "properties": raw_schema.get("properties", {}),
        "required": raw_schema.get("required", []),
    }

    # 1. inline $ref
    parameters = inline_refs(parameters, defs)

    # 2. 禁止 additionalProperties
    force_no_additional_properties(parameters)

    return {
        "type": "function",
        "function": {
            "name": name or model.__name__,
            "description": description or (model.__doc__ or ""),
            "parameters": parameters,
        },
    }


if __name__ =="__main__":
    import json
    print(json.dumps(basemodel_to_openai_tool_schema(ClickAction), indent=4, ensure_ascii=False))
    print(json.dumps(basemodel_to_openai_tool_schema(TypeAction), indent=4, ensure_ascii=False))
    print(json.dumps(basemodel_to_openai_tool_schema(ScrollAction), indent=4, ensure_ascii=False))
    print(json.dumps(basemodel_to_openai_tool_schema(DragAction), indent=4, ensure_ascii=False))
    print(json.dumps(basemodel_to_openai_tool_schema(AskAction), indent=4, ensure_ascii=False))
    print(json.dumps(basemodel_to_openai_tool_schema(WaitAction), indent=4, ensure_ascii=False))
    print(json.dumps(basemodel_to_openai_tool_schema(FinishedAction), indent=4, ensure_ascii=False))

