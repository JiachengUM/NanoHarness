"""分离出不含任何车控的case数据集。
判据：case_id / tags / expected_script / user_query_lists 里若涉及车控操作（空调/座椅/车窗/天窗/灯光/后视镜/除霜/雨刮/方向盘加热/遮阳帘/冰箱/香氛/氛围灯/阅读灯/HUD/屏幕/音量/4D音效/声场等硬件控制），则视为车控case，排除。

注意：
- 媒体播放（音乐/电台/USB）不算车控
- 导航不算车控
- 记忆/提醒/对话能力不算车控
- 音量调节算车控（硬件控制）
"""
import json
from pathlib import Path

SRC = Path(r"d:\yitu_projects\nanoai\projects\mind\mem\auto_test_script\make_datasets_for_vehicle_assistant\artifacts\projects\benz_project\cases\vehicle_assistant_cases.json")
DST = Path(r"d:\yitu_projects\nanoai\projects\mind\mem\auto_test_script\make_datasets_for_vehicle_assistant\artifacts\projects\benz_project\cases\vehicle_assistant_cases_no_car_control.json")

# 车控关键词（按硬件域分类）
CAR_CONTROL_KEYWORDS = [
    # 空调/温度/风量/风向
    "空调", "温度", "风量", "风向", "暖风", "冷风", "除霜", "除雾", "A/C",
    # 座椅
    "座椅", "座位", "靠背", "腰托", "座垫",
    # 车窗/天窗/遮阳帘
    "车窗", "天窗", "遮阳帘", "遮物帘", "后备箱", "尾门",
    # 灯光
    "氛围灯", "阅读灯", "大灯", "远光", "近光", "转向灯", "雾灯", "日行灯", "车灯",
    # 后视镜
    "后视镜",
    # 雨刮
    "雨刮", "雨刷",
    # 方向盘
    "方向盘加热",
    # 冰箱
    "冰箱",
    # 香氛
    "香氛", "香薰",
    # HUD/屏幕
    "HUD", "抬头显示", "屏幕亮度", "显示屏",
    # 音量/音效（硬件控制）
    "音量", "4D音效", "4D", "声场",
    # 座椅通风/按摩
    "通风", "按摩", "加热",  # "加热"可能歧义（座椅加热/方向盘加热），但车控里出现就是车控
    # 车门/锁
    "车门", "门锁", "锁车",
    # 空气净化
    "空气净化", "PM2.5",
]

# 媒体/导航/对话类关键词，不算车控（即使含"播放"等词）
MEDIA_KEYWORDS = ["播放", "暂停", "切歌", "下一首", "上一首", "收藏", "歌单", "电台", "USB", "音乐", "歌曲", "歌手", "专辑"]


def has_car_control(case: dict) -> tuple[bool, str]:
    """返回 (是否含车控, 命中原因)"""
    # 检查 case_id
    case_id = case.get("case_id", "")
    for kw in CAR_CONTROL_KEYWORDS:
        if kw in case_id:
            return True, f"case_id命中'{kw}'"

    # 检查 tags
    tags = case.get("tags", [])
    car_control_tags = [
        "温度直接设定", "温度增减调节", "空调模式切换", "空调开关", "风量增减调节", "风量直接设定", "风向调节",
        "座椅加热开关控制", "座椅加热档位调节", "座椅通风开关控制", "座椅通风档位调节", "座椅按摩模式调节", "座椅模式类型切换",
        "车窗开合度控制", "车窗开关控制", "多窗控制", "天窗开合度控制", "天窗开关控制", "遮阳帘开合度控制",
        "氛围灯颜色调节", "氛围灯开关", "氛围灯模式切换", "阅读灯亮度增减调节", "阅读灯亮度直接设定",
        "后视镜加热开关", "除霜除雾开关控制",
        "方向盘加热开关控制", "方向盘加热档位调节",
        "冰箱温度直接设定",
        "香氛类型切换", "香氛浓度调节",
        "媒体音量调节",  # 音量是硬件控制
        "4D音效开关", "声场模式调节",
        # 注意：导航音量调节也算车控（硬件音量）
        "导航音量调节",
    ]
    for tag in tags:
        if tag in car_control_tags:
            return True, f"tag命中'{tag}'"

    # 检查 expected_script 和 user_query_lists 的用户台词
    es = case.get("expected_script", "")
    # 只检查用户说的内容（用户：开头行），不检查管家：（助手）行
    # 因为助手可能提到"空调已调到24度"是执行结果反馈，但用户台词里提到才是测试车控
    user_lines = []
    for line in es.split("\n"):
        if line.startswith("用户：") or line.startswith("用户："):
            user_lines.append(line)
    # 也检查 user_query_lists
    for session in case.get("user_query_lists", []):
        for turn in session:
            if turn.get("role") == "user":
                user_lines.append(turn.get("content", ""))

    user_text = "\n".join(user_lines)

    # 特殊处理："音量"单独出现可能是媒体音量，但也算车控
    for kw in CAR_CONTROL_KEYWORDS:
        if kw in user_text:
            return True, f"用户台词命中'{kw}'"

    # 检查 case_description
    desc = case.get("case_description", "")
    # case_description 里描述的是测试目的，如果明确提到车控域则排除
    car_control_desc_keywords = [
        "空调", "温度", "风量", "座椅", "车窗", "天窗", "遮阳帘", "氛围灯", "阅读灯",
        "后视镜", "除霜", "除雾", "雨刮", "方向盘加热", "冰箱", "香氛", "音量",
        "4D音效", "声场", "HUD", "屏幕亮度"
    ]
    for kw in car_control_desc_keywords:
        if kw in desc:
            return True, f"case_description命中'{kw}'"

    return False, ""


def main():
    data = json.loads(SRC.read_text(encoding="utf-8"))
    no_car_control = []
    car_control = []
    for c in data:
        is_cc, reason = has_car_control(c)
        if is_cc:
            car_control.append((c, reason))
        else:
            no_car_control.append(c)

    DST.write_text(json.dumps(no_car_control, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"总计 {len(data)} 条")
    print(f"  无车控: {len(no_car_control)} 条 → {DST.name}")
    print(f"  含车控: {len(car_control)} 条（已排除）")
    print()
    print("=== 含车控case列表 ===")
    for c, r in car_control:
        print(f"  [{c.get('id')}] {c.get('case_id')} | {r}")


if __name__ == "__main__":
    main()
