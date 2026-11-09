import aiohttp
import asyncio
import requests
from projects.mind.advisor.domain_data import EpisodicMemory, VehicleState, VisualExterior, VisualInterior, EventBase, WorldInfo, UserBase
from projects.mind.advisor.advisors.comfort import ComfortAdviser
from projects.mind.advisor.utils.preprocess import read_file_from_folder
from colorama import init, Fore, Style
init(autoreset=True)  # 自动重置颜色


def generator(path):
    for name, data in read_file_from_folder(folder=path).items():
        if name == "user.json":
            user = UserBase(**data) or None
        if name == "world_info.json":
            world_info = WorldInfo(**data) or None
        if name == "memory.json":
            memory = EpisodicMemory(**data) or None
        if name == "vehicle_state.json":
            vehicle_state = VehicleState(**data) or None
        if name == "visual_int.json":
            visual_int = VisualInterior(**data) or None
        if name == "visual_ext.json":
            visual_ext = VisualExterior(**data) or None

    # event = EventBase(event="车辆启动了空调系统")
    # event = EventBase(event="苏苏作为乘客正在看书")
    event = EventBase(event="主驾上车了")
    # event = EventBase(event="苏苏作为乘客在擤鼻涕")

    advisor = ComfortAdviser()
    res = asyncio.run(advisor.run(world_info=world_info, memory=memory, vehicle_state=vehicle_state, visual_int=visual_int, visual_ext=visual_ext, user=user, event=event))
    print(res)


def read_local_context():
    df = dict()
    for name, data in read_file_from_folder("src/data/").items():
        if name == "world_info.json":
            df["world_info"] = data
        if name == "user.json":
            df["user"] = data
        if name == "memory.json":
            df["memory"] = data
        if name == "vehicle_state.json":
            df["vehicle_state"] = data
        if name == "visual_int.json":
            df["visual_int"] = data
        if name == "visual_ext.json":
            df["visual_ext"] = data
    df["event"] = "主驾上车了"
    return df


advisor = ComfortAdviser()


async def quick_local_process(context_list):
    """简化版本，避免复杂的列表推导式"""
    if not context_list:
        return {}

    # 直接构建任务列表
    tasks = []
    names = []

    for name, context in context_list.items():
        # 获取协程对象
        coro = advisor.quick_run(context=context)
        tasks.append(coro)
        names.append(name)

    # 并发执行
    try:
        results = await asyncio.gather(*tasks)
    except Exception as e:
        print(f"Error in asyncio.gather: {e}")
        # 调试：打印每个任务的类型
        for i, task in enumerate(tasks):
            print(f"Task {i} ({names[i]}): {type(task)}")
        raise

    # 返回结果字典
    return dict(zip(names, results))


async def quick_url_process(context_list):
    """使用 aiohttp 进行异步HTTP请求"""
    if not context_list:
        return {}

    results = {}

    async with aiohttp.ClientSession() as session:
        tasks = []
        names = []

        for name, context in context_list.items():
            # 创建异步任务
            task = session.post(
                "http://localhost:8001/v1/advise/comfort/quick",
                json={"context": context}
            )
            tasks.append(task)
            names.append(name)

        # 并发执行所有请求
        responses = await asyncio.gather(*tasks)

        # 处理响应
        for name, response in zip(names, responses):
            if response.status == 200:
                result = await response.json()
                results[name] = result
            else:
                results[name] = f"HTTP Error: {response.status}"
            response.close()
    return results


# 在main中调用
async def main():
    context_list = read_file_from_folder(folder="./tests_new/context", suffix=".txt")
    return await quick_url_process(context_list)


def print_enhanced_result(file, result_data):
    """增强格式打印结果"""
    data = result_data.get('result', {})
    current_issue = data.get('current_issue', '')
    suggestion = data.get('suggestion', '')

    # 分割建议为列表
    suggestions = []
    for item in suggestion.split(';'):
        if item.strip():
            suggestions.append(item.strip())

    print(f"\n{Fore.CYAN}{'=' * 70}")
    print(f"{Fore.YELLOW}📊 诊断报告")
    print(f"{Fore.CYAN}{'=' * 70}\n")

    print(f"{Fore.RED}{file} 当前问题：")
    print(f"{Fore.WHITE}{current_issue}\n")

    print(f"{Fore.GREEN}{file} 处理建议：")
    for i, sug in enumerate(suggestions, 1):
        print(f"{Fore.YELLOW}{i}. {Fore.WHITE}{sug}")
    print(f"\n{Fore.CYAN}{'=' * 70}")


if __name__ == "__main__":
    # 接口结构化处理
    # data = read_local_context()
    # response = requests.post("http://localhost:8001/v1/advise/comfort", json=data)
    # response = requests.post("http://localhost:8001/v1/advise/emotion", json=data)
    # print(response.json())

    # 本地读数据慢处理
    path = "./projects/mind/advisor/domain_data"
    generator(path=path)

    # 接口非结构化快速处理
    # result = asyncio.run(main())
    # for file, res in result.items():
    #     file = file.replace(".txt", "")
    #     print_enhanced_result(file, res)


