"""批量修复100条case中的存疑地址。

策略：
1. 识别所有"XX路N号"格式的具体门牌号地址
2. 白名单内的保留，白名单外的替换为泛指地点或白名单地址
3. 只改 expected_script 和 user_query_lists 里的用户台词，不改 car_info（car_info里的地址是预设上下文，允许保留）
4. 同步改 nl_assertion 里引用的地址
"""
import json
import re
from pathlib import Path

SRC = Path(r"d:\yitu_projects\nanoai\projects\mind\mem\auto_test_script\make_datasets_for_vehicle_assistant\artifacts\projects\benz_project\cases\vehicle_assistant_cases.json")
DST = SRC  # 覆盖原文件

# 白名单已验证地址（完整地址）
WHITELIST_ADDRS = [
    "上海市浦东新区世纪大道100号",
    "上海市黄浦区中山东一路",
    "上海市浦东新区陆家嘴环路1000号",
    "上海市黄浦区南京东路829号",
    "上海市黄浦区南京西路1266号",
    "杭州市西湖区文三路478号",
]

# 白名单路名（不带门牌号，允许使用）
WHITELIST_ROADS = ["南京西路", "南京东路", "淮海中路", "世纪大道", "花木路", "陆家嘴", "中山东一路", "文三路"]

# 知名地标（允许使用）
WHITELIST_LANDMARKS = [
    "上海中心大厦", "外滩", "东方明珠", "浦东国际机场", "虹桥国际机场", "虹桥火车站", "上海南站",
    "人民广场", "陆家嘴", "徐家汇", "静安寺", "迪士尼乐园", "上海环球金融中心", "金茂大厦", "恒隆广场",
    "嘉里中心", "来福士广场", "五角场", "天安门广场", "故宫", "杭州西湖", "苏州站", "浦东机场",
]

# 泛指地点（允许使用）
GENERIC_PLACES = ["公司", "家", "上次去的", "附近", "沿途"]


def find_suspicious_addresses(case: dict) -> list[tuple[str, str]]:
    """找出case中存疑的具体门牌号地址。
    
    返回 [(存疑地址, 上下文), ...]
    """
    suspicious = []
    
    # 检查 expected_script 和 user_query_lists
    texts_to_check = []
    
    # expected_script 的用户台词
    es = case.get("expected_script", "")
    if isinstance(es, str):
        for line in es.split("\n"):
            if line.startswith("用户："):
                texts_to_check.append(("expected_script用户台词", line))
    
    # user_query_lists
    for session in case.get("user_query_lists", []):
        for turn in session:
            if turn.get("role") == "user":
                texts_to_check.append(("user_query_lists", turn.get("content", "")))
    
    # nl_assertion
    for a in case.get("nl_assertion", []):
        texts_to_check.append(("nl_assertion", a))
    
    # 匹配"XX路N号"格式
    pattern = re.compile(r'[\u4e00-\u9fa5]{2,10}[路街道]\d+号')
    
    for ctx, text in texts_to_check:
        for m in pattern.findall(text):
            # 检查是否在白名单内
            is_whitelist = False
            for wa in WHITELIST_ADDRS:
                if m in wa or wa.endswith(m):
                    is_whitelist = True
                    break
            if not is_whitelist:
                suspicious.append((m, ctx))
    
    return suspicious


def fix_address(addr: str) -> str:
    """把存疑地址替换为安全的白名单地址或泛指地点。"""
    # 如果是"XX路N号"格式，替换为白名单地址
    # 根据原地址的城市特征，选合适的白名单地址
    if "莘庄" in addr or "春申" in addr or "闵行" in addr:
        return "上海市浦东新区世纪大道100号"
    elif "张江" in addr or "浦东" in addr:
        return "上海市浦东新区陆家嘴环路1000号"
    elif "干将" in addr or "苏州" in addr or "姑苏" in addr:
        return "杭州西湖"  # 改为知名地标
    elif "花木" in addr:
        return "上海市浦东新区世纪大道100号"
    else:
        # 默认替换为上海中心大厦（知名地标）
        return "上海中心大厦"


def fix_case(case: dict) -> tuple[dict, list[str]]:
    """修复case中的存疑地址，返回 (修复后case, 修改记录列表)"""
    changes = []
    suspicious = find_suspicious_addresses(case)
    if not suspicious:
        return case, changes
    
    # 构建替换映射
    replace_map = {}
    for addr, ctx in suspicious:
        if addr not in replace_map:
            replace_map[addr] = fix_address(addr)
    
    # 执行替换
    # 1. expected_script
    es = case.get("expected_script", "")
    if isinstance(es, str):
        for old, new in replace_map.items():
            if old in es:
                es = es.replace(old, new)
                changes.append(f"expected_script: '{old}' → '{new}'")
        case["expected_script"] = es
    
    # 2. user_query_lists
    for session in case.get("user_query_lists", []):
        for turn in session:
            if turn.get("role") == "user":
                content = turn.get("content", "")
                for old, new in replace_map.items():
                    if old in content:
                        content = content.replace(old, new)
                        changes.append(f"user_query_lists: '{old}' → '{new}'")
                turn["content"] = content
    
    # 3. nl_assertion
    new_assertions = []
    for a in case.get("nl_assertion", []):
        for old, new in replace_map.items():
            if old in a:
                a = a.replace(old, new)
                changes.append(f"nl_assertion: '{old}' → '{new}'")
        new_assertions.append(a)
    case["nl_assertion"] = new_assertions
    
    # 4. case_description
    desc = case.get("case_description", "")
    if isinstance(desc, str):
        for old, new in replace_map.items():
            if old in desc:
                desc = desc.replace(old, new)
                changes.append(f"case_description: '{old}' → '{new}'")
        case["case_description"] = desc
    
    return case, changes


def main():
    data = json.loads(SRC.read_text(encoding="utf-8"))
    
    total_changes = 0
    fixed_cases = 0
    
    for i, case in enumerate(data):
        case, changes = fix_case(case)
        data[i] = case
        if changes:
            fixed_cases += 1
            total_changes += len(changes)
            cid = case.get("id", "?")
            print(f"[{cid}] {len(changes)}处修改:")
            for ch in changes:
                print(f"  {ch}")
    
    DST.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n汇总: 修复{fixed_cases}个case, 共{total_changes}处地址替换")
    print(f"已覆盖: {DST}")


if __name__ == "__main__":
    main()
