import asyncio
import json
import os
from projects.mind.complex_reasoning.tools.Media import MediaTool
from projects.mind.complex_reasoning.tools.MusicSearch import MusicSearchTool
from projects.mind.complex_reasoning.tools.Websearch import WebsearchTool
from projects.mind.complex_reasoning.tools.Weather import WeatherTool
from projects.mind.complex_reasoning.tools.PoiSearch import PoiSearchTool
from projects.mind.complex_reasoning.tools.Navigate import NavigateTool
from projects.mind.complex_reasoning.tools.CarControl import CarControlTool

# 确保使用正确的文件路径
planner_file = os.path.join(os.path.dirname(__file__), '..', 'planner.jsonl')

async def test_planner():
    music_inputs = []
    navigate_inputs = []
    websearch_inputs = []
    carcontrol_inputs = []
    weather_inputs = []
    ret = dict()

    try:
        with open(planner_file, 'r', encoding='utf-8') as f:
            line_count = 0
            for line in f:
                line_count += 1
                try:
                    data = json.loads(line.strip())
                    output = data.get('output', "")
                    inputs = data.get('input', "")
                    domain = data.get('meta', {}).get('Domain')
                    Type = data.get('meta', {}).get('Type')
                    ret.setdefault(inputs, output)
                    if "音乐" in domain:
                        music_inputs.append(inputs)
                    if "新闻资讯" in domain:
                        websearch_inputs.append(inputs)
                    if '天气查询' in Type:
                        weather_inputs.append(inputs)
                    if "导航" in domain:
                        navigate_inputs.append(inputs)
                    if "车辆控制" in domain or "车辆控制" in Type:
                        carcontrol_inputs.append(inputs)
                except json.JSONDecodeError as e:
                    print(f"第 {line_count} 行解析失败: {e}")
                    continue
            print(f"文件读取完成，共 {line_count} 行")
    except Exception as e:
        print(f"文件读取失败: {e}")
        return


    music_tool = MusicSearchTool()
    for i, input_text in enumerate(music_inputs):
        break
        print(f"\n测试第 {i+1} 条输入: {input_text}")
        result = await music_tool.arun(input_text)
        print(f"测试结果: {result}")
        print(f"预期: {ret.get(input_text, '')}")
        break



    media_tool = MediaTool(chat_id="test_chat_id")
    for i, input_text in enumerate(music_inputs):
        break
        print(f"\n测试 {i + 1}: {input_text}")
        result = await media_tool.arun(input_text)
        print(f"状态: {result.status}")
        print(f"消息: {result.message}")
        print(f"观察: {result.observation}")
        print(f"错误信息: {result.error_msg}")
        print(f"预期: {ret.get(input_text, '')}")
        break


    websearch_tool = WebsearchTool()
    for i, query in enumerate(websearch_inputs):
        break
        print(f"\n测试第 {i} 条输入: {query}")
        result = await websearch_tool.arun(query)
        print(f"查询: {result.query}")
        print(f"结果数量: {len(result.references)}")
        print(f"消息: {result.message}")
        print(f"预期: {ret.get(query, '')}")
        break


    weather_tool = WeatherTool(chat_id="test_chat_id")
    for i, query in enumerate(weather_inputs):
        break
        print(f"\n测试第 {i} 条输入: {query}")
        result = await weather_tool.arun(query)
        # TODO 天气查询需要结合地址和天气意图来触发，地址是槽位
        #  所以planner.jsonl里面的天气询问都是类似“今天天气怎么样？”所以接口返回的是空槽位，用下面query来测天气接口
        # result = await weather_tool.arun("上海明天后天天气")
        print(f"结果: {result}")
        print(f"预期: {ret.get(query, '')}")
        break

    from time import time
    poi_tool = PoiSearchTool()
    for _ in range(5):
        start = time()
        for i, input_text in enumerate(navigate_inputs):
            if i == 0:
                continue
            result = await poi_tool.arun(input_text)
            print(f"输入: {input_text}")
            print(f"测试结果: {result}")
            print(f"预期: {ret.get(input_text, '')}")
            break
        end = time()
        process_time = end - start
        print(process_time)



    car_control_tool = CarControlTool(chat_id="test_chat_id")
    for i, input_text in enumerate(carcontrol_inputs):
        break
        print(f"\n测试第 {i+1} 条指令: {input_text}")
        result = await car_control_tool.arun(input_text)
        print(f"测试结果: {result}")
        print(f"预期: {ret.get(input_text, '')}")
        break


    print("创建NavigateTool实例...")
    tool = NavigateTool(chat_id="test_chat_id")
    for i, input_text in enumerate(navigate_inputs):
        break
        result = await tool.arun(input_text)
        print(f"输出: {result}")
        print(f"预期: {ret.get(input_text, '')}")
        break


if __name__ == "__main__":
    print("开始执行测试脚本")
    asyncio.run(test_planner())
    print("测试脚本执行完成")
