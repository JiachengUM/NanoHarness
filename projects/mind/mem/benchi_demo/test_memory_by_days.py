"""
按天数进行记忆管理的测试脚本
每天：添加记忆 -> 等待生效 -> 召回记忆
"""
import asyncio
from rich import print
from projects.mind.intent.task_data.message import Message
from projects.mind.mem.volc_api import (
    add_to_memory,
    SearchMemory,
    MemoryFilter,
    search_memory,
)

# 记忆库配置
MEMORY_COLLECTION_NAME = "SGM"
MEMORY_USER_ID = "user_890"
MEMORY_TYPES = ["profile_v1", "profile_device_v1", "profile_location_v1", "profile_music_v1"]
MEMORY_LIMIT = 10

# 等待时间（秒）- 让记忆生效（实测40秒都不太稳定，实际与messages数量有关）
WAIT_TIME = 40


async def add_and_recall_memory(
    day: int,
    messages: list[dict[str, str]],
    collection_name: str = MEMORY_COLLECTION_NAME,
    user_id: str = MEMORY_USER_ID,
) -> None:
    """添加记忆并召回记忆"""
    
    print(f"\n{'='*80}")
    print(f"[bold green]第 {day} 天[/bold green]")
    print(f"{'='*80}\n")
    
    # 1. 转换消息格式
    conversation = [Message(role=msg["role"], content=msg["content"]) for msg in messages]
    
    # 2. 添加记忆
    print(f"[yellow]步骤1: 添加记忆[/yellow]")
    print(f"对话内容:")
    for msg in conversation:
        print(f"  {msg.role}: {msg.content[:50]}..." if len(msg.content) > 50 else f"  {msg.role}: {msg.content}")
    
    await asyncio.to_thread(
        add_to_memory,
        conversation,
        collection_name=collection_name,
        user_id=user_id,
        session_id=f"day_{day}",
    )
    print(f"[green]✓ 记忆添加成功[/green]\n")
    
    # 3. 等待记忆生效
    print(f"[yellow]步骤2: 等待 {WAIT_TIME} 秒让记忆生效...[/yellow]")
    await asyncio.sleep(WAIT_TIME)
    print(f"[green]✓ 等待完成[/green]\n")
    
    # 4. 召回记忆
    print(f"[yellow]步骤3: 召回记忆[/yellow]")
    search_request = SearchMemory(
        collection_name=collection_name,
        query=None,  # 空查询，召回所有记忆
        limit=MEMORY_LIMIT,
        filter=MemoryFilter(
            memory_type=MEMORY_TYPES,
            user_id=user_id,
        ),
    )
    
    try:
        memory_result = await asyncio.to_thread(search_memory, search_request)
        print(f"[green] 记忆召回成功[/green]")
        print(f"\n召回的记忆数量: {len(memory_result.data.result_list)}")
        
        if memory_result.data.result_list:
            print(f"\n记忆内容:")
            for i, item in enumerate(memory_result.data.result_list, 1):
                print(f"\n  [{i}] {item.memory_info}")
        else:
            print("  暂无记忆")
            
    except Exception as e:
        print(f"[red] 记忆召回失败: {e}[/red]")
    
    print(f"\n{'='*80}\n")


async def main():
    """主函数：按天数顺序处理所有对话"""
    
    # 第一天的对话
    day1_messages = [
        {"role": "user", "content": "记一下我做瑜伽的地方在闵行区顾戴路2468号"},
        {"role": "assistant", "content": "已帮你记录瑜伽馆地址：闵行区顾戴路2468号。下次需要导航过去可以随时告诉我哦～或者现在要帮你导航过去吗？"},
        {"role": "user", "content": "不用，导航到我爸妈家"},
        {"role": "assistant", "content": "好的，为你导航到爸妈家。不过我还不知道叔叔阿姨家的具体地址，麻烦告诉我一下详细地址（比如XX市XX区XX路XX号），我马上帮你规划路线～"},
        {"role": "user", "content": "万达广场3号楼"},
        {"role": "assistant", "content": "以下是多个结果，请问是第几个？1. 万达广场 3 号楼 上海市宝山区共和新路 4995 号宝山万达广场 3 号楼（共康路地铁站附近，楼下为招商银行） 2. 万达广场公寓 3 号楼 上海市松江区广富林路 658 弄 215 号万达广场 3 号楼 3. 万达广场江桥店 3 号写字楼 上海市嘉定区江桥镇金沙江西路 1069 号（金运路地铁站 1 号口步行 230 米，鹤旋路与华江公路交叉口西北侧） 4. 万达广场 3 号楼 (南门) 上海市松江区广富林路 658 弄 215 号万达广场 3 号楼南门"},
        {"role": "user", "content": "就第一个"},
        {"role": "assistant", "content": "好的，为你导航到宝山万达广场 3号楼"},
        {"role": "user", "content": "你帮我记一下我爸妈的地址吧"},
        {"role": "assistant", "content": "好的，已经帮你记下来了。"},
        {"role": "user", "content": "记一下我外婆家的地址在今天花园8号楼"},
        {"role": "assistant", "content": "已帮你记录外婆家地址：今天花园8号楼。下次需要导航过去可以随时告诉我哦～"},
        {"role": "user", "content": "播放周杰伦的稻香"},
        {"role": "assistant", "content": "好的，正在播放周杰伦的稻香。已为你播放周杰伦的《稻香》，需要调整音量或切换其他歌曲随时告诉我～"},
        {"role": "user", "content": "音量调高"},
        {"role": "assistant", "content": "音量已调高，当前音量是否合适？需要继续调整或切换其他歌曲吗？"},
        {"role": "user", "content": "今天天气怎样"},
        {"role": "assistant", "content": "今天上海市闵行区天气晴朗，气温10-20度，适合户外活动。"},
        {"role": "user", "content": "你知道周杰伦是我最喜欢的歌手不"},
        {"role": "assistant", "content": "哈哈，从你刚才点了周杰伦的歌，就猜到他是你的心头好了～需要我继续为你播放他的其他经典曲目吗，你还喜欢哪些？"},
        {"role": "user", "content": "喜欢蛮多的吧枫晴天七里香之类的，喜欢这些歌的歌词"},
        {"role": "assistant", "content": "周杰伦的中国风歌词确实很有韵味，《枫》的'缓缓飘落的枫叶像思念'、《晴天》的'故事的小黄花'，每一句都像在讲故事～需要我帮你播放这些歌吗？"},
    ]
    
    # 第二天的对话
    day2_messages = [
        {"role": "user", "content": "导航到重庆小面（九亭大街店）"},
        {"role": "assistant", "content": "好的，已为你规划前往重庆小面（九亭大街店）的路线。"},
        {"role": "user", "content": "导航到外婆家"},
        {"role": "assistant", "content": "请问你是想导航到外婆家餐厅的哪个具体门店呢？比如外婆家（上海维璟印象城店）或者其他分店？"},
        {"role": "user", "content": "导航到我外婆家"},
        {"role": "assistant", "content": "导航已开启，正在为你指引前往今天花园8号楼的路线，请注意行驶安全～"},
        {"role": "user", "content": "算了导航到我外婆家附近比较好吃的餐厅吧，帮我推荐一个"},
        {"role": "assistant", "content": "为你推荐今天花园8号楼附近的三家餐厅：\n1. 剪花娘子（小吃快餐，评分3.8，人均25元）\n2. 东方华宴（中餐，评分4.5，人均242元）\n3. 鸿熹荟·海鲜融合菜餐厅（宁波菜，评分4.4，人均139元）\n请问你想选择哪家餐厅导航过去呢？"},
        {"role": "user", "content": "导航到东方华宴吧，刚好我爱吃那里的红烧肉，我老婆爱吃辣可以给她点辣的，女儿也能吃些茶点"},
        {"role": "assistant", "content": "导航已开启，正在为你指引前往东方华宴的路线，预计行驶时间约34分钟，如有其他需求随时告诉我哦～"},
        {"role": "user", "content": "导航到重庆小面（九亭大街店）"},
        {"role": "assistant", "content": "好的，已为你规划前往重庆小面（九亭大街店）的路线。"},
    ]
    
    # 第三天的对话
    day3_messages = [
        {"role": "user", "content": "导航到重庆小面（九亭大街店）"},
        {"role": "assistant", "content": "好的，已为你规划前往重庆小面（九亭大街店）的路线。"},
        {"role": "user", "content": "我冬天喜欢开28摄氏度"},
        {"role": "assistant", "content": "明白了，冬天空调偏好是28度。"},
        {"role": "user", "content": "夏天开24摄氏度空调"},
        {"role": "assistant", "content": "明白了，夏天空调偏好是24度。"},
        {"role": "user", "content": "打开空调"},
        {"role": "assistant", "content": "好的，正在帮你打开空调。"},
        {"role": "user", "content": "空调温度调到28摄氏度"},
        {"role": "assistant", "content": "好的，已经帮你调到28摄氏度。"},
        {"role": "user", "content": "空调风量调到二档"},
        {"role": "assistant", "content": "好的，已经帮你调到二档。"}
    ]
    
    # 第四天的对话
    day4_messages = [
        {"role": "user", "content": "导航到重庆小面（九亭大街店）"},
        {"role": "assistant", "content": "好的，已为你规划前往重庆小面（九亭大街店）的路线。"},
        {"role": "user", "content": "打开空调"},
        {"role": "assistant", "content": "好的，正在帮你打开空调。"},
        {"role": "user", "content": "空调温度调到28摄氏度"},
        {"role": "assistant", "content": "好的，已经帮你调到28摄氏度。"},
        {"role": "user", "content": "空调风量调到二档"},
        {"role": "assistant", "content": "好的，已经帮你调到二档。"}
    ]
    
    # 第五天的对话
    day5_messages = [
        {"role": "user", "content": "打开空调"},
        {"role": "assistant", "content": "好的，正在帮你打开空调。"},
        {"role": "user", "content": "空调温度调到28摄氏度"},
        {"role": "assistant", "content": "好的，已经帮你调到28摄氏度。"},
        {"role": "user", "content": "空调风量调到二档"},
        {"role": "assistant", "content": "好的，已经帮你调到二档。"}
    ]
    
    # 第六天的对话
    day6_messages = [
        {"role": "user", "content": "打开空调"},
        {"role": "assistant", "content": "好的，正在帮你打开空调。"},
        {"role": "user", "content": "空调温度调到28摄氏度"},
        {"role": "assistant", "content": "好的，已经帮你调到28摄氏度。"},
        {"role": "user", "content": "空调风量调到二档"},
        {"role": "assistant", "content": "好的，已经帮你调到二档。"}
    ]
    
    # 第七天的对话
    day7_messages = [
        {"role": "user", "content": "我女儿今年6岁啦，她准备过生日啦送点什么合适"},
        {"role": "assistant", "content": "益智类：乐高 / 拼图 ；阅读类：带拼音的桥梁书；运动类：儿童自行车 / 滑板车；兴趣类：可水洗画笔 / 过家家套装；纪念类：刻名儿童手表，请问你女儿是否有特别喜欢的礼物？"},
        {"role": "user", "content": "她比较喜欢运动吧，我想送她去打网球"},
        {"role": "assistant", "content": "那优先选网球相关的实用礼物，兼顾兴趣和使用需求，极简推荐这 3 个：儿童专用网球拍：选 6 岁适配的轻量款，握柄细、拍面适中，颜色挑她喜欢的。；可爱运动装备：速干运动套装 + 带名字的儿童运动水壶，打球穿戴方便又有专属感。；亲子网球体验课：直接送一节入门体验课，陪她一起玩，能快速激发她对网球的兴趣。；需要我帮你整理一份儿童网球装备选购清单吗？"},
        {"role": "user", "content": "好的，带她去买球拍吧，附近有什么好的商场吗？她生日就1月10号，快到了早点准备吧"},
        {"role": "assistant", "content": "去七宝万科广场吧，那里有很多运动品牌，还有亲子乐园，适合带孩子去逛逛。"},
        {"role": "user", "content": "我结婚10周年也要到了，1月15号，送点什么合适"},
        {"role": "assistant", "content": "结婚纪念日礼物可以考虑一些有纪念意义的东西，比如定制的情侣对戒、情侣手链、情侣项链等。也可以考虑一些浪漫的礼物，比如浪漫的晚餐、浪漫的旅行、浪漫的SPA等。也可以考虑一些实用的礼物，比如浪漫的晚餐、浪漫的旅行、浪漫的SPA等。"},
        {"role": "user", "content": "那我送她一个浪漫的晚餐吧"},
        {"role": "assistant", "content": "好的，我可以帮你安排一个浪漫的晚餐，包括烛光晚餐、玫瑰花、红酒等。"},
        {"role": "user", "content": "我再想想，不急。"}
    ]
    
    # 第八天的对话
    day8_messages = [
        {"role": "user", "content": "我老婆喜欢吃辣，我喜欢吃清淡的广东菜，去哪吃呢"},
        {"role": "assistant", "content": "去维璟印象城吧，那里有很多广东菜，还有辣菜，适合你们去尝尝。"},
        {"role": "user", "content": "好吧"},
        {"role": "assistant", "content": "我帮你导航到维璟印象城。"}
    ]
    
    # 第九天的对话（修改）
    day9_messages = [
        {"role": "user", "content": "最近觉得王菲蛮好听的，可惜她不会再开演唱会了"},
        {"role": "assistant", "content": "王菲的歌确实很有韵味，空灵的嗓音太经典啦～虽然演唱会难等，但她的专辑和live版歌曲还是能常听常新的～需要我帮你播放她的经典曲目吗？比如《红豆》《传奇》这些？"},
        {"role": "user", "content": "播放一下百年孤寂吧"},
        {"role": "assistant", "content": "《百年孤寂》已为你播放～王菲的这首歌旋律和歌词都很有故事感，需要帮你调整音量或者切换其他她的歌曲吗？"},
        {"role": "user", "content": "喜欢这个歌手"},
        {"role": "assistant", "content": "王菲的音乐确实很有独特魅力，她的很多歌曲都值得反复品味～需要我帮你继续播放她的其他经典作品吗？比如《匆匆那年》《暧昧》这些热门曲目？"}
    ]
    
    # 第十天的对话（修改）
    day10_messages = [
        {"role": "user", "content": "最近还挺爱吃辣的，我还以为我吃不了辣呢"},
        {"role": "assistant", "content": "哈哈，看来你的味蕾解锁新技能啦！吃辣确实很上头～需要我帮你搜索附近口碑不错的川菜馆或者湘菜馆吗？"},
        {"role": "user", "content": "去张园附近的那个潇湘阁吧"},
        {"role": "assistant", "content": "导航已为你开启，将带你前往潇湘阁（张园店）～途中需要调整路线偏好（比如避开拥堵/走高速）或者播放点适合下饭的音乐吗？"}
    ]
    
    # 第十一天的对话（修改）
    day11_messages = [
        {"role": "user", "content": "导航到爸妈家"},
        {"role": "assistant", "content": "好的，为你导航到宝山万达广场 3号楼"},
        {"role": "user", "content": "不对不对，爸妈搬家了搬到田林养老了，住气象苑"},
        {"role": "assistant", "content": "好的，为你导航到徐汇区气象苑"}
    ]
    
    # 第十二天的对话（删除）
    day12_messages = [
        {"role": "user", "content": "我听腻了王菲了，不喜欢了"},
        {"role": "assistant", "content": "好的，那我帮你换一些其他歌手的音乐，或者你想听听什么类型的音乐呢？流行、摇滚、民谣还是别的？"},
        {"role": "user", "content": "最近没兴趣做瑜伽了，别存着我做瑜伽的地址了，我的卡都到期了"},
        {"role": "assistant", "content": "明白了，已经帮你从记忆中移除瑜伽相关的地址信息，如果你以后需要再添加，随时告诉我哦。"}
    ]
    
    # 按天数顺序处理
    all_days = [
        (1, day1_messages),
        (2, day2_messages),
        (3, day3_messages),
        (4, day4_messages),
        (5, day5_messages),
        (6, day6_messages),
        (7, day7_messages),
        (8, day8_messages),
        (9, day9_messages),
        (10, day10_messages),
        (11, day11_messages),
        (12, day12_messages),
    ]
    
    for day_info in all_days:
        day = day_info[0]
        messages = day_info[1]
        await add_and_recall_memory(day, messages)
    
    print(f"\n处理完成！]\n")


if __name__ == "__main__":
    asyncio.run(main())