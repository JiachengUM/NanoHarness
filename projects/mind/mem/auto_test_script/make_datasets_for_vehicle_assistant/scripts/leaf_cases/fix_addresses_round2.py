"""第二轮修复：处理管家括号块和case_description里残留的存疑地址引用。"""
import json
import re
from pathlib import Path

SRC = Path(r"d:\yitu_projects\nanoai\projects\mind\mem\auto_test_script\make_datasets_for_vehicle_assistant\artifacts\projects\benz_project\cases\vehicle_assistant_cases.json")
data = json.loads(SRC.read_text(encoding="utf-8"))

REPLACE_MAP = {
    "上海市浦东新区张江路100号": "上海市浦东新区陆家嘴环路1000号",
    "张江路100号": "上海市浦东新区陆家嘴环路1000号",
    "春申路1080号": "上海市浦东新区世纪大道100号",
    "海市闵行区莘庄镇春申路1080号": "上海市浦东新区世纪大道100号",
    "花木路1378号": "上海市浦东新区世纪大道100号",
    "干将东路178号": "杭州西湖",
    "苏州市姑苏区干将东路178号": "杭州西湖",
    "中山东一路28号": "上海中心大厦",
    "去南京西路1266号": "上海中心大厦",
    "户澄清目的地为南京西路1266号": "户澄清目的地为上海中心大厦",
}

changes = 0
for i, case in enumerate(data):
    cid = case.get("id", "?")
    for field in ["expected_script", "case_description"]:
        text = case.get(field, "")
        if not isinstance(text, str):
            continue
        for old, new in REPLACE_MAP.items():
            if old in text:
                text = text.replace(old, new)
                changes += 1
                print(f"[{cid}] {field}: {old} -> {new}")
        case[field] = text
    data[i] = case

SRC.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"\n第二轮修复: {changes}处")
