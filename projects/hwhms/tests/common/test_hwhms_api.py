import asyncio
import sys
import time
import uuid
from pathlib import Path

import requests

sys.path.append(str(Path(__file__).parent.parent.parent.parent.parent))

from projects.hwhms.common import volcengine_api


def generate_test_data(car_type: str = "CAR_A"):
    """生成测试数据，每次调用时生成新的UUID"""
    return [
        {"query":"今天有什么热点新闻", "history":[], "chat_id":str(uuid.uuid4()), "question_id":str(uuid.uuid4()), "car_type":car_type},
        {"query":"设置空调温度为26度", "history":[], "chat_id":str(uuid.uuid4()), "question_id":str(uuid.uuid4()), "car_type":car_type},
        {"query":"暂停音乐", "history":[], "chat_id":str(uuid.uuid4()), "question_id":str(uuid.uuid4()), "car_type":car_type},
        {"query":"切换到收音机频道", "history":[], "chat_id":str(uuid.uuid4()), "question_id":str(uuid.uuid4()), "car_type":car_type},
        {"query":"关闭车窗", "history":[], "chat_id":str(uuid.uuid4()), "question_id":str(uuid.uuid4()), "car_type":car_type},
        {"query":"什么是雨刷器", "history":[], "chat_id":str(uuid.uuid4()), "question_id":str(uuid.uuid4()), "car_type":car_type},
        {"query":"多久换一次雨刮条", "history":[], "chat_id":str(uuid.uuid4()), "question_id":str(uuid.uuid4()), "car_type":car_type},
        {"query":"空气悬架是什么意思", "history":[], "chat_id":str(uuid.uuid4()), "question_id":str(uuid.uuid4()), "car_type":car_type},
        {"query":"雨刷器怎么使用", "history":[], "chat_id":str(uuid.uuid4()), "question_id":str(uuid.uuid4()), "car_type":car_type},
        {"query":"如何正确使用安全带", "history":[], "chat_id":str(uuid.uuid4()), "question_id":str(uuid.uuid4()), "car_type":car_type},
        {"query":"你好", "history":[{"q":"你好", "a":"你好"}], "chat_id":str(uuid.uuid4()), "question_id":str(uuid.uuid4()), "car_type":car_type},
        {"query":"今天天气怎么样", "history":[{"q":"昨天天气怎么样", "a":"昨天天气晴朗"}], "chat_id":str(uuid.uuid4()), "question_id":str(uuid.uuid4()), "car_type":car_type},
        {"query":"帮我算一下1+1等于几", "history":[{"q":"怎么打开香氛", "a":"香氛系统已打开"}], "chat_id":str(uuid.uuid4()), "question_id":str(uuid.uuid4()), "car_type":car_type},
        {"query":"推荐一部好看的电影", "history":[{"q":"推荐一部好看的电视剧", "a":"好的，以为你推荐XXXXX"}], "chat_id":str(uuid.uuid4()), "question_id":str(uuid.uuid4()), "car_type":car_type},
        {"query":"农历多少", "history":[{"q":"今天几号了", "a":"今天几号了"}], "chat_id":str(uuid.uuid4()), "question_id":str(uuid.uuid4()), "car_type":car_type},
        {"query":"去年9月8号是什么节日", "history":[], "chat_id":str(uuid.uuid4()), "question_id":str(uuid.uuid4()), "car_type":car_type},
        {"query":"你是谁", "history":[], "chat_id":str(uuid.uuid4()), "question_id":str(uuid.uuid4()), "car_type":car_type},
        {"query":"你爸爸是谁", "history":[], "chat_id":str(uuid.uuid4()), "question_id":str(uuid.uuid4()), "car_type":car_type},
        {"query":"距离春节还有多少天", "history":[], "chat_id":str(uuid.uuid4()), "question_id":str(uuid.uuid4()), "car_type":car_type},
      ]

def generate_news_data():
    return [
        # {"query":"今天有什么热点新闻", "history":[]},
        # {"query":"今天有哪些重要新闻", "history":[]},
        # {"query":"有什么热点新闻吗", "history":[]},
        # {"query":"和我说说今天的新闻头条吧", "history":[]},
        # {"query":"昨天的热点新闻是什么", "history":[]},
        # {"query":"8月份有什么热点新闻", "history":[]},
        # {"query":"有关于特朗普的相关新闻吗", "history":[]},
        # {"query":"美国总统大选最新新闻", "history":[]},
        # {"query":"关于AI的最新新闻", "history":[]},
        # {"query":"有什么娱乐新闻", "history":[]},
        # {"query":"和我说说今天的新闻头条吧", "history":[]},
        # {"query":"昨天的热点新闻是什么", "history":[]},
        # {"query":"8月份有什么热点新闻", "history":[]},
        # {"query":"有关于特朗普的相关新闻吗", "history":[]},
        # {"query":"美国总统大选最新新闻", "history":[]},
        # {"query":"关于AI的最新新闻", "history":[]},
        # {"query":"有什么娱乐新闻", "history":[]},
        # {"query":"说说军事新闻吧", "history":[]},
        # {"query":"我想听本地新闻", "history":[]},
        # {"query":"上海今天有什么新鲜事吗", "history":[]},
        # {"query":"我想听军事热点新闻", "history":[]},
        # {"query":"看看北京最新的房产资讯吧", "history":[]},
        # {"query":"我想用喜马拉雅听热点新闻", "history":[]},
        # {"query":"打开喜马拉雅听头条", "history":[]},
        # {"query":"我想在喜马拉雅上听有关于特朗普的新闻", "history":[]},
        # {"query":"我想在喜马拉雅上收听美国总统大选事件脉络。", "history":[]},
        # {"query":"我要在喜马拉雅上听体育新闻.", "history":[]},
        # {"query":"帮我用喜马拉雅播放2023年11月23日的新闻", "history":[]},
        # {"query":"杀手是什么身份？", "history":[]},
        # {"query":"这个新闻想表达什么", "history":[]},
        # {"query":"帮我梳理下这个问题的前因后果", "history":[]},
        # {"query":"特朗普竞选遇刺的杀手是什么身份？", "history":[]},
        # {"query":"我对美国总统大选的背景和当前情况都很感兴趣，帮我回顾下。", "history":[]},
        {"query":"播放第2条", "history":[{"q":"今日重点新闻", "a":"\"\\n\\n003cp003e为您梳理了今日热点，商务部将召开新闻发布会介绍近期商务领域重点工作。您对商务动态感兴趣吗？003c/p003e\\n003clh003e1、商务部将召开新闻发布会003c/lh003e\\n003clp003e10月16日下午3时，商务部将举行新闻发布会，介绍近期商务领域重点工作。003c/lp003e\\n003clu003e20251016A01PRK00003c/lu003e\\n003clh003e2、台湾光复纪念日确立003c/lh003e\\n003clp003e中共中央通过决议，将10月25日定为台湾光复纪念日。003c/lp003e\\n003clu003e20251025A01EQ400003c/lu003e\\n003clh003e3、国台办举行例行新闻发布会003c/lh003e\\n003clp003e国台办新任发言人彭庆恩首次主持发布会，介绍对台方针政策。003c/lp003e\\n003clu003e20251029A022YC00003c/lu003e\\n003cy003e了解商务部新闻发布会的具体议题。003c/y003e003cy003e台湾光复纪念日设立的背景是什么？003c/y003e003cy003e彭庆恩新任发言人的政策立场有哪些？003c/y003e\"" }]},
        {"query":"播放第1条", "history":[

		{

		"q": "今日热点新闻",

		"a": "\"\\n\\n003cp003e今日热点新闻速递，医保即时结算改革即将全面铺开。003c/p003e\\n003clh003e1、医保即时结算改革推进003c/lh003e\\n003clp003e国家医保局要求2025年底前全国所有统筹地区均需开展医保基金即时结算，以提升结算效率。003c/lp003e\\n003clu003e20251017A02TPS00003c/lu003e\\n003clh003e2、商务部回应美对中造船调查003c/lh003e\\n003clp003e中方将依法推进诉讼，商务部将推动服务消费扩大，并回应美方贸易措施。003c/lp003e\\n003clu003e20251017A02TGT00003c/lu003e\\n003clh003e3、现货黄金突破4330美元/盎司003c/lh003e\\n003clp003e受多重因素影响，现货黄金价格突破4330美元/盎司关口，日内涨幅明显。003c/lp003e\\n003clu003e20251017A02LTJ00003c/lu003e\\n003cy003e医保即时结算将如何影响患者就医费用？003c/y003e003cy003e美对中造船调查后续进展如何？003c/y003e003cy003e目前黄金投资的主要影响因素有哪些？003c/y003e\""

		}]},
        
    ]

async def test_volc_api():
    data = generate_news_data()
    for item in data:
        result = await volcengine_api.volcengine_intent(item['query'], item['history'])
        print(result)
        


def test_hwhms_api():
    """
    测试HWHMS API接口
    
    注意：需要先启动hwhms的api服务，运行 main.py 文件 (\projects\hwhms\main.py)
    """
    url = "http://127.0.0.1:18992/v1/exturing/chat/intent/chat/completions"
    ##url = "http://101.126.11.190/hwhms-nanoai-agent-dev/v1/exturing/chat/intent/chat/completions"
    headers = {
        "Authorization": "Bearer lNTZIiZXf_-uwfTE1z2oQM5RekCl94GuiHFTb3ntnK5XAguc-SWrB6hQBUHybggHFYko-iPDAGexPgPdexINizhEQGBGyDeBlOOcFxZQvTEI52tfBeUfJhkV-ADH57QlLrjJxtSV8VUsVIC1hFSB61vOF4rNEDi2kwoc6I",
        "Content-Type": "application/json"
    }
    
    data = generate_test_data(car_type="CAR_B")
    
    for idx, item in enumerate(data, 1):
        try:
            # 构建请求体，使用 messages 字段包装
            payload = {"messages": item}
            start_time = time.time()
            response = requests.post(url, json=payload, headers=headers, timeout=3)
            
            if response.status_code == 200:
                print(f"[{idx}/{len(data)}] ✓ Query: {item['query']}")
                result = response.json()
                print(f"  response: {result}")
                print(f"  耗时: {time.time() - start_time}秒")
            else:
                print(f"[{idx}/{len(data)}] ✗ Query: {item['query']}")
                print(f"  Error: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"[{idx}/{len(data)}] ✗ Query: {item['query']}")
            print(f"  Exception: {str(e)}")
        print()

if __name__ == "__main__":
    ##test_hwhms_api()
    asyncio.run(test_volc_api())
