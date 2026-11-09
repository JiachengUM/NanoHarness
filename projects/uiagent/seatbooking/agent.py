from pathlib import Path
import os
from datetime import datetime
import json
from prompts.seatbooking_prompts import DECISIONS_TRANSLATION, ROUTE_NODE_PROMPT,SEARCHING_RESTAURANT_SPECIFIC_MISSON_DISCRIPTION,CONFIRM_SEAT_BOOKING_PERSON_INFO_PROMPT,BOOKING_DETAIL_MISSON_DISCRIPTION,TRY_TO_CLICK_SEAT_BOOKING_NODE_DISCRIPTION,render_reflect_prompt,render_mission_prompt
from pydantic_models.seatbooking_agent_pydantic_models import AgentOutputResponse,ActionInfo, AgentInputRequest, OverallState
from uiagent.model.uitars import ui_tars_client
from utils.utils import encode_image, parse_and_draw_action,pars_reflect_output
from tqdm import tqdm
# 定义节点
def route_node(state: OverallState) -> OverallState:
    """决策下一个动作是哪个业务处理节点的路由节点"""
    # TODO 判断当前应该使用哪个业务处理节点处理当前的输入
    stages="["+",".join(DECISIONS_TRANSLATION.keys())+"]"
    route_node_prompt = ROUTE_NODE_PROMPT.format(stages=stages)
    messages = []
    try:
        if state.view_image_url.startswith("http"):
            message = {
            "role": "user",
            "content": [
                {"type": "text", "text": route_node_prompt},
                {"type": "image", "url": state.view_image_url},
                ]
            }
        else:
            image_base64 = encode_image(state.view_image_url)
            image_type = Path(state.view_image_url).suffix[1:]
            state.encoded_image = image_base64
            state.image_type = image_type
            message = {
            "role": "user",
            "content": [
                {"type": "text", "text": route_node_prompt},
                {
                    "type": "image",
                    "base64": state.encoded_image,
                    "mime_type": "image/"+state.image_type,
                },
                ]
            }
        messages.append(message)
        response = ui_tars_client.invoke(messages)
    except Exception as e:
        print(e)
        raise e
    stage = response.content.split("Stage: ")[1].strip()
    if stage not in set(DECISIONS_TRANSLATION.keys()):
        raise Exception(f"{stage}不存在于{DECISIONS_TRANSLATION.keys()}之中")
    state.decision = stage
    print("下一个业务处理节点是："+state.decision)
    return state
    
def act_node(state: OverallState):
    """订座人信息确认节点"""
    back_ground_info = f"当前时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}"
    if state.decision == "订座人信息":
        specific_misson_discription = CONFIRM_SEAT_BOOKING_PERSON_INFO_PROMPT
    elif state.decision == "订座":
        specific_misson_discription = BOOKING_DETAIL_MISSON_DISCRIPTION
    elif state.decision == "找店":
        specific_misson_discription = SEARCHING_RESTAURANT_SPECIFIC_MISSON_DISCRIPTION
    elif state.decision == "点订座":
        specific_misson_discription = TRY_TO_CLICK_SEAT_BOOKING_NODE_DISCRIPTION
    prompt = render_mission_prompt(specific_misson_discription=specific_misson_discription, previous_info=state.previous_thought, back_ground_info=back_ground_info, history=state.history)
    messages = []
    if state.view_image_url.startswith("http"):
        message = {
        "role": "user",
        "content": [
            {"type": "text", "text": prompt},
            {"type": "image", "url": state.view_image_url},
            ]
        }
    else:
        message = {
        "role": "user",
        "content": [
            {"type": "text", "text": prompt},
            {
                "type": "image",
                "base64": state.encoded_image,
                "mime_type": "image/"+state.image_type,
            },
            ]
        }
    messages.append(message)
    state.main_prompt = messages
    response = ui_tars_client.invoke(messages)
    print("*****************************************")
    print(response.content)
    print("*****************************************")
    cache_image_file_name = str(state.trace_id) + ".png"
    cache_dir_path_with_file = os.path.join(state.image_cache_path, cache_image_file_name)
    print(cache_dir_path_with_file)
    print("@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@")
    action_info = ActionInfo(**parse_and_draw_action(image_path=state.view_image_url,content_to_parse=response.content,output_path=cache_dir_path_with_file)[0])
    print("+++++++++++++++++++++++++++++++++++++++++")
    print(action_info)
    state.next_action = action_info
    state.next_thought = action_info.thought
    state.main_prompt = str(messages)
    action_info_string = "action_type: "+action_info.action_type+"\n"+"action_inputs: "+str(action_info.action_inputs)
    print("+++++++++++++++++++++++++++++++++++++++++")
    if state.need_reflection:
        # 使用大模型对自己的动作输出以及渲染图做一次审视和判断，把判断结果可以写到某个地方当做统计结果，然后还输出反思的结果，如果反思后认为是错误的，那么给出意见
        # 并且再次加入反思意见后继续尝试生成一次动作
    # 先查看state里image cache文件是否存在
        if cache_dir_path_with_file and Path(cache_dir_path_with_file).exists():
            reflect_prompt = render_reflect_prompt(action_info=action_info_string, previous_info=state.previous_thought, specific_misson_discription=specific_misson_discription, back_ground_info=back_ground_info, history=state.history)
            image_base64 = encode_image(cache_dir_path_with_file)
            image_type = Path(cache_dir_path_with_file).suffix[1:]
            messages = []
            message = {
            "role": "user",
            "content": [
                {"type": "text", "text": reflect_prompt},
                {
                    "type": "image",
                    "base64": image_base64,
                    "mime_type": "image/"+image_type,
                },
                ]
            } # 标准message格式
            messages.append(message)
            response = ui_tars_client.invoke(messages)
            print("——————————————————————————反省原始输出——————————————————————————————————")
            print(response.content)
            print("————————————————————————————————————————————————————————————")
            reflect_result,reflect_advice = pars_reflect_output(content_to_parse=response.content)
            print(".....................反省结果.......................")
            print(reflect_result)
            print(reflect_advice)
            print("............................................")
            if state.store_reflection_result:
                # 把反省结果存下来
                state.reflection_result = reflect_result
                state.reflection_advice = reflect_advice
            if reflect_result == "wrong":
                # 反思后认为动作输出错误，那么在加入反思内容后重新思考并输出一遍动作
                prompt = render_mission_prompt(specific_misson_discription=specific_misson_discription,reflection=reflect_advice, previous_info=state.previous_thought, back_ground_info=back_ground_info, history=state.history)
                messages = []
                if state.view_image_url.startswith("http"):
                    message = {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image", "url": state.view_image_url},
                        ]
                    }
                else:
                    message = {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image",
                            "base64": state.encoded_image,
                            "mime_type": "image/"+state.image_type,
                        },
                        ]
                    }
                messages.append(message)
                response = ui_tars_client.invoke(messages)
                cache_image_file_name = str(state.trace_id) + "_reflected.png"
                cache_dir_path_with_file = os.path.join(state.image_cache_path, cache_image_file_name)
                action_info = ActionInfo(**parse_and_draw_action(image_path=state.view_image_url,content_to_parse=response.content,output_path=cache_dir_path_with_file)[0])
        else:
            # 如果不存在，可选择抛出异常或创建默认路径
            raise FileNotFoundError(f"指定的image cache路径不存在: {cache_dir_path_with_file}")
    state.next_action = action_info
    return state

class SeatbookingAgent:
    def __init__(self):
        self.state = OverallState(image_cache_path="projects/uiagent/seatbooking/cache/image_cache/")

    def run(self,agent_input:AgentInputRequest):
        """运行智能体"""
        # 根据AgentInputRequest，更新state
        self.state.trace_id = agent_input.trace_id
        self.state.previous_thought = agent_input.previous_thought
        self.state.view_image_url = agent_input.view_image_url
        self.state.history = agent_input.history
        self.state.need_reflection = agent_input.need_reflection
        self.state.store_reflection_result = agent_input.store_reflection_result
        self.state = route_node(self.state)
        self.state = act_node(self.state)

        output = AgentOutputResponse(
            trace_id=self.state.trace_id,
            next_action=self.state.next_action,
            next_thought=self.state.next_thought,
            reflection_result=self.state.reflection_result,
            reflection_advice=self.state.reflection_advice,
            main_prompt=self.state.main_prompt,
        )
        return output

def evaluate(dataset_file_path:str,evaluate_result_path:str):
    """评估智能体在数据集上的表现"""
    result_file_name = dataset_file_path.split("/")[-1].replace(".json","_result.json")
    result_file_path = os.path.join(evaluate_result_path,result_file_name)
    with open(result_file_path, "a", encoding="utf-8") as of:
        with open(dataset_file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
            total_num = 0
            correct_num = 0
            result_list = []
            # 使用tqdm包装循环，展示进度
            for line in tqdm(lines, desc="评估进度"):
                data = json.loads(line)
                trace_id = data["id"]
                previous_thought = data["query"]
                view_image_url = data["image_path"]
                agent_input = AgentInputRequest(
                    trace_id=trace_id,
                    previous_thought=previous_thought,
                    view_image_url=view_image_url,
                    history=[],
                    need_reflection=True,
                    store_reflection_result=True,
                )
                agent = SeatbookingAgent()
                agent.state.image_cache_path = evaluate_result_path
                output = agent.run(agent_input=agent_input)
                total_num += 1
                if output.reflection_result == "right":
                    correct_num += 1
                result_list.append(str(output.__dict__))
            print("total_num is ",total_num)
            print("correct_num is ",correct_num)
            correct_rate = f"{float(correct_num / total_num) * 100:.2f}%"
            of.write("correct rate is "+correct_rate + "\n\n")
            for an_item in result_list:
                of.write(json.dumps(an_item, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    # 直接测试
    # messages = []
    # message = {
    #     "role": "user",
    #     "content": [
    #         {"type": "text", "text": "这个图描述了什么？"},
    #         {"type": "image", "url": "http://47.117.182.61/test_result_img/result_2025-10-15_22-18-41/dingzuo_info.jpg"},
    #         ]
    #     } # 标准message格式
    # messages.append(message)
    # response = ui_tars_client.invoke(messages)
    # print(response.content)
    # exit()

    # agent = SeatbookingAgent()
    # start_user_message = {
    #     "role": "user",
    #     "content": [
    #         {"type": "text", "text": "我叫张先生"},
    #     ]
    # }
    # history=[]
    # history.append(start_user_message)
    # output = agent.run(agent_input=AgentInputRequest(
    #     trace_id="1",
    #     previous_thought="订个10月18日 12:15 的座位",
    #     view_image_url="http://47.117.182.61/test_result_img/result_2025-10-15_22-18-41/dingzuo_info.jpg",
    #     history=history,
    #     need_reflection=True,
    #     store_reflection_result=False,
    # ))
    # print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
    # print(output.trace_id)
    # print(output.main_prompt)
    # print(output.next_thought)
    # print(output.next_action.action_type)
    # print(output.next_action.action_inputs)
    # print(output.reflection_result)
    # print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")

    evaluate(
        dataset_file_path="projects/uiagent/seatbooking/references/output.jsonl",
        evaluate_result_path="projects/uiagent/seatbooking/tests/output",
    )

    
