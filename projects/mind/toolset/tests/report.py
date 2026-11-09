import json
import pandas as pd
import asyncio
from rich import print
from aicore.agents.experiments.user_profile import (
    UserProfile,
    SINGLE_CAREER_WOMAN,
    RETIRED_SENIOR,
    STARTUP_YOUTH,
    FULL_TIME_MOM,
    BUSINESS_ELITE,
)

from aicore.models.credentials import create_client, AsyncArk, ModelName
from aicore.agents.experiments.base import AgentBase, ResponseParams, RunParams
from projects.mind.toolset import get_default_tools, get_prompt as system_prompt

# 获取工具列表
tools = get_default_tools(chat_id="test_chat")

import csv
from projects.mind.toolset.tests.fetch_datasets import fetch_all
input_file = './report/data/user_queries.csv'
# input_file = './report/data/bad_case_test_samples.csv'

car_state_path = "./report/data/car_state.json"
with open(car_state_path, 'r', encoding='utf-8') as f:
    car_state = json.load(f)

memory_path = "./report/data/memory.json"
with open(memory_path, 'r', encoding='utf-8') as f:
    user_memory = json.load(f)

def get_data():
    # filter_strings = ["帮我按照北京欢迎你这首歌里面的路线安排一个行程，然后路上找个适合喝咖啡的地方，同时先帮我把空调调一下",
    #                   "我要去东方明珠玩，然后先回家接一下我女儿，帮我先播放我喜欢听的音乐，等我女儿上车之后就播放她喜欢的音乐，最后找一个我们都喜欢吃的餐厅",
    #                   "我要去上班，帮我找几首流行的歌曲，然后根据天气调一下车辆",
    #                   "我要出去兜兜风，帮我规划一下",
    #                   "我想明天去金鸡湖玩"]
    ret = []
    # 读取并处理CSV文件
    with open(input_file, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        headers = next(reader)
        for i, row in enumerate(reader, start=1):
            try:
                # ret.append(dict(zip(headers, row)))
                ret.append({"query":"，".join([query for query in row if query])})
            except Exception as e:
                print(f'解析第 {i} 行时出错: {e}')
    return ret


async def dump_agent_data(query, agent: AgentBase):
    async for _ in agent.astream(query, event_listeners=[]):
        pass
    dump_data = await agent.dump()
    system_msg = ""
    assistant_msg = ""
    tool_call_input = []
    tool_call_output = []
    for item in dump_data.model_dump()["history"]:
        role = item.get("role", "")
        if role == "system":
            system_msg = item["content"][0]["text"]
        elif role == "assistant":
            assistant_msg = item["content"][0]["text"]
        elif item.get("name", ""):
            tool_call_input.append({item["name"]: item["arguments"]})
        else:
            if item["type"] == "function_call_output":
                tool_call_output.append(item["output"])
    return system_msg, assistant_msg, tool_call_input, tool_call_output


async def process_query(data_item, run_params):
    try:
        # 将context合并到system的role字段中
        # TODO case越来越多时需要回归测试skill
        # TODO 系统提示词内容可以被打包成AGENT.md放到对应项目下，
        #  系统提示词优化是harness工程的一部分，优化思路是将具体badcase内容抽象成四种情况：
        #  【不可以做xxx】、【可以做xxx】、【当xxx时，可以做xxx】，【当xxx时，不可以做xxx】
        # system_prompt = SystemPrompt(
        #     role="你是车载助手，完全遵循用户要求，回复时保持极简极简极简极简。\n\n车辆状态：\n{car_state}\n\n用户偏好：\n{user_memory}".format(car_state=car_state, user_memory=user_memory),
        #     guidelines=[
        #         # "注意区分地点类型和店名"
        #         # "调用工具前，简短回复打算做什么",
        #         "原则上使用车辆状态和用户偏好",
        #         # TODO 已修复历史天气无法查询
        #         "weather_agent只能查询当前或未来",
        #         # TODO 【评测skill优化，N个模糊意图是否都同时满足】已修复长文本含有出行需求未关注到的问题
        #         "出行和自媒体相关的都需要被合理回复",
        #         "音乐场景可以利用车辆状态和用户偏好进行适当联想和关联，推荐但不执行",
        #         "别忘了音乐执行控制和推荐理由",
        #         # "qq_music_song_search歌手不能超过3个",
        #         "周边搜索必须提供地址",
        #         # TODO 【评测skill优化，时间不敏感】增加了出发时间，修复了【我明天去xxx地方】，Navigation的输入有出发时间，接口识别‘今天’并返回正确的date作为出发日期
        #         "有明确导航意图并且有目的地和触发时间时直接导航",
        #         "歌曲播放支持单首，歌单包含多首歌曲",
        #         "当用户询问歌单时，将歌曲整理成歌单",
        #         "最新歌曲或榜单指的是最近public_time",
        #         # "联网检索时不对模糊时间表达做具体时间转换，最近指的是一周一年？反问用户？",
        #         # "播放歌单前询问？",
        #         # "执行车控前先获取当前车端状态",
        #         # "执行工具前先检查【记忆】再行动",
        #         "联网检索时不做模糊POI检索、垂直领域（电商、本地生活攻略）",
        #         # TODO 优化了工具参数缺失直接跳过调用，增加【如缺失，就不要调用】
        #         "打算调用工具前，请仔细思考用户是否提供了足够调用工具的信息。如缺失，就不要调用，礼貌地询问用户获取缺失信息。询问要简短，不要罗列工具细节",
        #     ],
        # )
        agent = AgentBase(system_prompt(), run_params=run_params, tools=tools)
        # 执行异步数据转储
        system_msg, assistant_msg, tool_input, tool_output = await dump_agent_data(data_item["query"], agent)
        data_item["system_msg"] = system_msg
        data_item["assistant_msg"] = assistant_msg
        data_item["tool_input"] = tool_input
        data_item["tool_output"] = tool_output
        return data_item
    except Exception as e:
        data_item["query"] = "-".join(["ERROR", data_item["query"], str(e)])
        data_item["system_msg"] = None
        data_item["assistant_msg"] = None
        data_item["tool_input"] = None
        data_item["tool_output"] = None
        print(f"处理查询失败：{data_item['query']}: {str(e)}")
        return data_item

async def run():
    # files = await fetch_all()
    # for name, data in files.items():
    data = [
        # TODO 可搜索停车场类型，附近默认设置成了3公里以内，符合常识
        # "上海世博园附近商场",
        # "上海浦东新区世博园附近的商场",
        "湊湊火锅·茶憩(莘庄维璟印象城店)的特色有哪些？",
        "找一家附近的火锅店，4分以上，有停车场的",
        # TODO business返回的店面评分接口文档说明中指出仅在餐饮、酒店、景点、影院类 POI 下返回，但摩托车服务一级标题下也有评分
        "哈雷摩托车普陀店的评分和人均消费多少",
        "附近最近的地下停车场",
        # TODO 做了意图澄清
        "酒店停车场是地下还是地面的？",
        # TODO 能拿到联系方式和人均消费
        "蟠龙天地景点的评分是多少？联系电话有吗？",
        "找一家附近的火锅店，告诉我营业时间和人均消费",
        # TODO 具体地址搜通过text搜索入口将地址通过关键词搜
        "盒马鲜生(莘庄维璟印象城店）在几楼？",
        "上海虹桥火车站安检口在哪个楼层？",
        # TODO 无工具可查询卫生间
        "上海博物馆的洗手间分布图有吗？",
        # TODO 有具体地址时直接导航
        "怎么从上海南京东路地铁站走到上海国家博物馆入口？",
        # TODO 给出了精确位置以及坐标点，不太稳定
        "给我闵行中心医院急诊部的精确坐标",
        # TODO 进入了周边搜索，语义上是，但现实中可能需要返回闵行万象城的停车场，进入text搜索试试
        "闵行万象城附近最方便的停车场入口在哪？",
        # TODO 关键词为商场，停车场为筛选项，此时无法返回停车场类型，需要根据常识推理商场带有停车场
        "附近有停车场的商场",
        "带我去附近的充电站",
        # TODO "有明确导航意图并且有目的地和触发时间时直接导航，否则搜索结果只能作为推荐或未来规划"，去掉“有明确导航意图”
        "找个附近3公里以内性价比最高的川菜馆，帮我导航过去",
        # TODO 测一下北京过来的朋友会不会被误识别
        "有没有公司附近的酒店，有个朋友从北京过来，推荐一个500元左右的",
        "我昨晚一直在听啥，是谁唱的呀，来点差不多风格的，重新放这首",
        "想找找能延续我常听风格的近期全新曲目",
        "我最近听了什么歌，谁唱的，他还有什么歌，播放最新的，换最近听的那个首",
        # TODO 模糊时间转换
        "最近有什么好听的新歌推荐",
        # TODO 模糊时间转换
        "帮我挖掘下近期发行、适合我循环播放的歌曲",
        "车内太干，看点车内养生知识，查看日常调理贴士，筛选换季专属内容，逐条语音朗读，收藏整套资讯",
        "我要去幼儿园接我老婆",
        "我要周杰伦的歌",
        # TODO 目前为MediaTool直接生成歌单，MediaTool能力依赖具体车型，无法测试
        "我要周杰伦的歌，整理成歌单",
        # TODO 待测
        # "省考有最新消息吗，搜索对应相关的新闻",
        # "全国跟我姓一样的有几个",
        # "这地方最近有啥新闻",
        "推荐几个值得去的旅游城市，并导航前往目的地",
        "帮我查一下适合旅游的城市，顺便规划路线导航过去",
        "帮我搜搜哪些城市适合旅游并导航去哪",
        "我想按照北京欢迎你这首歌里面的景点游玩一下北京，帮我弄一下",
        "我要出去兜兜风，帮我规划一下，随便兜兜风，心情不好",
        "带我随便逛逛",
        # "明天的空气质量如何",
          ][:1]
    data = [{"query": row} for row in data]
    client, model = create_client(ModelName.SEED_1_8_251228, AsyncArk)
    params = ResponseParams(thinking={"type": "disabled"})
    run_params = RunParams(
        model=model,
        params=params,
        max_turns=5
    )
    tasks = [process_query(data_item, run_params) for data_item in data]
    results = await asyncio.gather(*tasks)
    return results
        # csv_file_path = "./report/data/{name}.csv".format(name=name)
        # pd.DataFrame(results).to_csv(csv_file_path, index=False, encoding="utf-8-sig")
        # print(f"结果已保存至: {csv_file_path}")
        # print(f"处理了 {len(data)} 条数据，成功 {len(results)} 条")


if __name__ == "__main__":
    print(asyncio.run(run()))