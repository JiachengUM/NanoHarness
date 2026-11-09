#!/usr/bin/env python3
import sys
import json
import asyncio
import argparse
import time
from pathlib import Path
from typing import Optional

# 加到 d:\yitu_projects\nanoai 根目录，使 from nanoai.model.llm import allm_output 可用
sys.path.insert(0, str(Path(__file__).resolve().parents[7]))

from pydantic import BaseModel, Field
from nanoai.model.llm import allm_output
from nanoai.model.config import ModelName
from full_case_audit import load_and_assemble_prompt, CaseAudit, _filter_cases, _extract_num, _load_guideline, _build_tag_validation_info, _fmt_duration, _merge_audit_principles, PROJECT_ROOT

MAX_FIX_ROUNDS = 5

# 重试先导段（强制保留，奔驰项目特有）：所有 case 的 expected_script 必须以此开头
# 审核修复 LLM 常会误删先导段，修复后必须兜底补回（奔驰项目写作原则§2.1.7 / 通用审核原则§F4 + 奔驰项目审核补充§6）
# 先导段含两部分：1) 重试规则（管家耳背时假人重试）；2) 能力受限不纠缠规则（管家表示无法执行时假人不再反复尝试）
RETRY_PREAMBLE = "管家可能耳背，有时听不到导致没能回复你，那么你扮演用户时如果发现管家没说话的话，你可以重试最多3次，每次重试时都需要在指令前加上固定的唤醒词“你好，你好奔驰”，且你可以把除了唤醒词之外的内容换各种同义说法重试。另外如果管家明确表示当前无法执行你的指令（比如要求车辆处于特定状态、请你自己手动操作、当前功能受限、需要先满足某些前置条件等），那就不要再反复尝试了，直接接受现状，不要继续追问或换说法重试。"

# 演员应变规则（强制保留，紧接重试先导段之后）
# 写作原则§7.3.8 / 审核原则§F4b
# 含两部分：1) 盲选第一个（助手让选列表时假人盲选第一个，避免逐一念候选名）；2) 简洁回复承接（助手只说"好的"时假人直接继续下一句台词，裁判从log核对执行结果）
BLIND_PICK_RULE = "另外特别提醒：你作为演员虽然能看到车机log，但直接从屏幕列表里逐一念候选名再选既浪费时间又可能选错。所以当助手让你选择目的地、POI候选、歌曲版本等任何需要从屏幕列表里挑一个的情况时（比如导航后助手给出多个候选让你选），你都直接盲选第一个就行，说“第一个”或“选第一个”即可，不要逐一念候选名，也不要问“我选哪个”之类的话，也不要无视助手的提问直接念下一句台词。"
SIMPLE_CONTINUE_RULE = "还有一点很重要：当助手的回复能明确反映执行结果时（比如“已将空调调到24度”“正在导航到北京野生动物园”），就直接继续下一句台词；如果助手只说“好的”“收到”“已为您处理”这类无实质内容的礼貌回复，没说具体做了什么，你也直接继续下一句台词就行——不需要追问确认，因为裁判会从车机log核对助手是否真的执行了你的指令。"
FULL_PREAMBLE = RETRY_PREAMBLE + "\n\n" + BLIND_PICK_RULE + "\n\n" + SIMPLE_CONTINUE_RULE


def _ensure_preamble(expected_script: str) -> str:
    """兜底：检查 expected_script 是否以重试先导段开头，若被删除则自动补回。
    若已有先导（即使后续被改写），不重复补，避免出现两份先导。
    """
    if not isinstance(expected_script, str) or not expected_script:
        return FULL_PREAMBLE + "\n\n"
    if expected_script.startswith(RETRY_PREAMBLE):
        return expected_script
    # 兼容：如果开头是相近的"管家可能耳背"前导（被轻微改写），保留现有，不覆盖
    if expected_script.startswith("管家可能耳背"):
        return expected_script
    # 先导被删除 → 补回
    return FULL_PREAMBLE + "\n\n" + expected_script.lstrip()


def _apply_preamble_safeguard(case: dict) -> dict:
    """对修复后的 case 应用先导段兜底，确保 expected_script 仍以先导开头。
    在 LLM 修复返回后调用，避免修复 LLM 误删先导段。
    """
    if not isinstance(case, dict):
        return case
    es = case.get("expected_script")
    if isinstance(es, str):
        new_es = _ensure_preamble(es)
        if new_es != es:
            case["expected_script"] = new_es
    return case


FIX_PROMPT_TEMPLATE = '''
你是一个车机助手评测用例修复专家。你的任务是根据审核反馈修复一个有问题的case。

【修复规范来源——三者必须一致】
1. 审核原则（下方「审核本质原则」）——审核依据什么，修复就照什么改
2. 合成规范（下方「case合成规范」）——case 结构、user_query_lists、expected_script、nl_assertion、tags 的写法
3. 打标指南（下方全文）——标签必须与叶子定义一致

【审核本质原则】
以下审核原则由两部分组成，项目级原则优先于通用原则：
1. 通用审核原则（来自 _shared_case_audit_principles.md）
2. 项目级审核原则覆盖（来自 case_audit_supplements.md，优先级更高，冲突时以项目级为准）

---

{{CASE_AUDIT_PRINCIPLES}}

---

【case合成规范（来自SKILL.md核心要点）】
1. user_query_lists 每项 = 一次独立冷启动 = 仅第一条 user 消息。同会话第2轮起的用户台词全部写在 expected_script 的「用户：」行里。绝对不能在 user_query_list 里放 assistant 消息或多条 user 消息。
2. 如果助手需要追问，流程是：user_query_lists 里放用户的首条消息 → expected_script 里写「管家：（期望助手追问xxx）」→ 紧接「用户：（回答助手的问题）」→ 再接「管家：（期望助手确认记录xxx）」
3. tags 必须包含至少3类：产品功能类叶子 + 通用对话能力类叶子 + 结构/难度类叶子。不能只打通用对话和结构标签而缺产品功能标签。具体来说：如果case涉及记忆/偏好/澄清等交互体验能力，必须打「交互体验与记忆」子树下的叶子（如「上下文不足触发澄清」「模糊需求追问」「直接记录」「间接记录」等）；如果涉及车控，必须打「车控操作」子树下的叶子；以此类推。
4. 「多次多轮_N次会话」标签要求每次会话都是多轮对话（至少2轮），如果某次会话只有1轮用户消息，不要打这个标签，改打「多次单轮_N次会话」或调整会话结构使其成为多轮。
5. 记忆类case必须「生产→消费」闭环：前几会话完成写入/纠错/更新记忆，最后一会话发消费型指令验证助手是否调用记忆。消费轮禁止泄题——不能复述生产轮内容，不能暗示有历史记忆。
5b. 【闭环前置原则·通用】所有依赖「用户偏好/历史记忆/当前媒体状态/当前车辆任务状态/已建立的任务上下文」等前提条件的 case，必须通过对话生产前提条件，再在后续轮次或后续会话中消费并验证。禁止用 car_info 预设来代替对话建立前提。适用三类场景：(1)媒体状态类——询问当前歌曲/歌手/播放内容、收藏、切歌、暂停、音量调节、播放模式切换、播放进度控制等，须先通过对话播放再询问/控制；(2)用户偏好/记忆类——调用用户喜欢的颜色/歌手/食物等偏好，须先通过对话建立偏好记忆再消费；(3)任务上下文类——基于已建立任务状态进行追问/修改/取消/状态查询（如导航状态查询"还有多久到"），须先通过对话启动任务再询问。两种实现结构：单会话多轮前置（前提与消费在同会话，user_query_lists 为 [[前提, 消费]]）；多次多轮前置（跨会话，user_query_lists 为 [[前提], [消费]]，expected_script 用"（重启新的对话……）"分隔）。car_info 仅用于客观硬件/环境状态（位置、时间、档位、车速、温度、硬件、已安装应用等）。
6. 仅「直接记录」叶子用「记住：…」口吻；其他记忆叶子（对话事实、稳定偏好、规律发现等）不用「记住」，而是自然带出事实或重复行为。
7. nl_assertion 每条必须有本case唯一的判定结果。通用结构约束（如"第二会话为独立冷启动""助手不得使用暗示连续聊天的措辞""前言不搭后语"）换任何多会话case都成立，没有区分力，必须删除或替换为具体判据。正确写法：直接说本case里助手该做到什么，如"第一会话须追问具体店名，不得直接记录模糊的「最常去咖啡店」"。
   【nl_assertion写法正反例】
   反例（无区分力，换任何case都成立）：
   - "助手回复须与用户请求属于同一任务，不得答非所问" → 万能描述，任何case都适用
   - "助手须体现可判定的任务推进结果" → 万能描述
   - "助手回复须包含执行信息或判断依据" → 万能描述
   - "助手不得给出模糊承诺" → 万能描述
   正例（有区分力，只在本case成立）：
   - "助手须将「回家」解析为前滩住址并推进导航" → 只在这条case成立
   - "助手须追问具体咖啡店名称，不得直接记录模糊的「最常去咖啡店」" → 只在这条case成立
   - "第二会话助手须根据已记录的空调关闭偏好主动关闭空调" → 只在这条case成立
   写法公式：[会话编号]+[具体操作对象]+[具体期望行为]+[具体禁止行为]
   【硬性规则】每条nl_assertion必须包含至少一个具体的操作对象（如具体的歌名、地点名、温度值、操作名称、设备名），不能只用"任务""请求""核心""场景""能力"等抽象词。如果一条断言把具体操作对象替换成XX后仍然通顺，说明它没有区分力。
   【禁止万能兜底】断言中禁止加"若有歧义则先澄清""如需确认则追问""如有必要则补充"等万能兜底——这些条件分支让断言在任何结果下都能成立，等于没有断言。断言必须只描述本case里助手该做到的唯一正确行为。
   【有意义的通用底线 vs 无意义的废话断言】nl_assertion允许包含通用底线约束，前提是它对车载助手场景有实际意义、导演能据此勾Pass/Fail。
   ✅ 有意义的通用底线（允许保留）：导演能明确判断Pass/Fail，且对车载助手场景有实际约束力。如"助手不得答非所问""助手不得口出污言秽语""助手不得仅给出无实质内容的礼貌性回复"。
   ❌ 无意义的废话断言（必须删除）：看似在提要求，实则不知所云、导演无法据此勾Pass/Fail。如"打开/关闭/调节/切换等动作之一"（万能列举=什么都没说）、"需体现可判定的任务推进结果"（"可判定"本身就是空话）、"需包含执行信息或判断依据"（什么算"执行信息"？）、"须明确体现对XX语义的落地承接（如A、B、C、D等）"（罗列所有可能性=没说任何一种）。
   判断标准：问自己"导演能根据这条断言明确勾Pass还是Fail吗？"如果能，是有意义的通用底线；如果不能，是无意义的废话断言。
   关键原则：nl_assertion必须同时有通用底线约束和case专属断言。如果审核反馈说某条断言"为通用要求""无区分力"，判断它是有意义的底线还是无意义的废话——有意义的底线可保留（但需确保有case专属断言配合），无意义的废话必须删除。
   【断言宁少勿多】nl_assertion 2-4条高质量专属断言+1-2条有意义的通用底线约束远胜于5条全是无意义废话的列表。
8. nl_assertion 违禁条必须用"不得"开头，不能写成正向要求（如"生成挑动对立文案"等于要求作恶）。
9. nl_assertion 只评助手行为，不评"用户该怎么念"。如"用户吐槽须与...可对照"是在规范用户行为，不是断言，必须删除或改为评助手。
10. 问题复盘类case（A7原则）：验证轮用户只能弱托付（如重复同一简问"照旧/你知道咋办吧"），不能把改进方向念出来。如果用户说了"盯着点导航信息""别再晚提醒"等改进方向，等于剧透，绕过了验证助手是否自己记住改进诉求的能力。
11. expected_script 管家括号块写「期望助手xxx」，不是命令。不能写万能模板套话（如"完成生产侧内容""完成消费/复核/诱导验证"），必须写本case里期望助手具体做什么。【2026-08-11新增】管家括号块**不得**强制助手口头详细反馈执行结果——删除"须明确反馈""须明确告知""须明确说明""须明确回答""须明确回复""须详细说明"等措辞及配套期望台词示例（如"如'已为您调到22度'"），只保留核心动作描述（"须执行XXX""须追问XXX"等）和禁止性约束（"不得XXX"）。裁判现在能从车机log核对执行结果，助手只说"好的"也应当判通过。
12. 【强制保留重试先导段】expected_script 开头有一段统一的重试先导段（以"管家可能耳背"开头，含"你好奔驰"唤醒词），这是合法的人设/规则前导段。**修复时必须原样保留，不得删除、改写、压缩或移动位置**。修复后的 expected_script 必须仍以该先导段开头，先导段后用空行分隔正文。
13. 【电话类 case 不应纳入自动测试集】电话类 case（涉及拨打电话的 case）**无法自动测试**——被测助手拨通电话后进入通话态，麦克风采集的用户语音被切到电话通道，被测助手无法聆听后续指令，假人说"挂断"也传不到助手。若修复时发现 case 涉及拨打电话（user_query_lists 或 expected_script 中出现"打电话""拨打""拨号""呼叫"等），**不要**用加挂断台词的方式修复（挂断指令传不到助手），应在 audit_issues 中标记该 case 不适合自动测试。
14. 【功能操作型指令须先构建任务态】存在一类"功能操作型指令"——它们本身不发起任务，而是对**已运行任务**做操作/查询/设置。如果冷启动直接说这类指令，被测助手面对的是"无任务进行中"的状态，操作无对象，评测不可复现。典型裸指令（以导航为例）：「刷新路线」「放大地图」「缩小地图」「2D车头朝上」「3D车头朝上」「切换为详细播报」「打开实时路况」「删除第一个途经点」「下一个收费站多远」「前方堵车吗」「目的地是哪里」「到目的地多远」等。其他域同理：媒体控制类（"切歌""暂停""音量调大"）需先播放，任务状态查询（"当前播放什么""导航到哪了"）需先建立对应任务。**修复方法**：在 expected_script 前序轮次（或新增冷启动 session）补上任务建立过程——导航类补"导航到XXX"建立导航任务，媒体类补"播放XXX"建立播放状态。途经点操作类还需先"添加YYY为途经点"（删除"第一个/第二个"类需要≥2个途经点才有区分度）。完整生命周期：构建任务态 → [按需补充操作对象] → 验证操作 → 恢复原状（见第15条）。**注意**：优先用"补前置轮次"的方式修复，不要改写原始冷启动台词（除非台词本身就是问题根源）。
15. 【状态恢复闭环】会改变车上软硬件长期状态的 case（媒体播放/导航任务/车控操作/定时任务等），expected_script 末尾须增加"恢复轮"，通过自然口语指令尝试恢复原状，避免残留状态污染后续 case。恢复指令示例：媒体"暂停播放/先别放了"、导航"退出导航/取消导航/不导了"、车控"关掉空调/车窗关上/氛围灯关了"、定时"取消刚才的提醒"。恢复轮用户台词须自然口语，不得说"为了不影响下一个测试""为了恢复初始状态"等导演话。恢复轮不计入核心 nl_assertion 判据，恢复失败也不影响本 case 判定（尽力而为）。不需要恢复轮的类别：纯查询类、S2S闲聊、拒识类、记忆类。max_round 须为前序核心轮次 + 恢复轮 + 重试余量。
16. 【地址必须真实存在，禁止编造】case 中出现的所有地址/地名/地标/POI 必须真实存在，不得编造。LLM 常见错误模式是"真实路名+编造门牌号"或"真实城市+编造路名"。**修复时**：若发现存疑地址（具体门牌号地址但不在白名单内），必须替换为白名单地址或改为泛指地点。白名单已验证地址：上海市浦东新区世纪大道100号、上海市黄浦区中山东一路、上海市浦东新区陆家嘴环路1000号、上海市黄浦区南京东路829号、上海市黄浦区南京西路1266号、杭州市西湖区文三路478号。知名地标（不需门牌号）允许使用：上海中心大厦、外滩、浦东机场、虹桥火车站、恒隆广场、杭州西湖等。泛指地点允许使用：公司、家、附近XX、沿途XX。

【修复执行检查清单——修复完必须逐项自检】
1. user_query_lists 每项是否只有一条 user 消息？如果有 assistant 消息或多条 user 消息，必须把后续轮次移到 expected_script。
2. expected_script 里用户行是否都是纯口语？如果有"说出希望下次如何改进""盯着点导航信息"等改进方向指令，必须改为弱托付（如重复同一简问）或纯吐槽（不提改进方向）。用户行不能有括号说明或导演话，必须是演员可以直接照读的短句口语。条件规律发现类case，用户台词不能泄露car_info中的条件变量（如"晴天听钢琴""外面下雨了"），用户只说偏好/操作，条件变量留给car_info。
3. nl_assertion 每条是否只评助手行为？如果有"用户须...""用户吐槽须..."等规范用户行为的条目，必须删除或改为评助手。
4. nl_assertion 是否同时包含通用底线约束和case专属断言？如果只有通用断言没有case专属断言，必须补充case专属断言。通用结构约束（如"第二会话为独立冷启动""不得使用暗示连续聊天的措辞"）不是底线约束，必须删除。
5. tags 是否包含产品功能类叶子？如果只有通用对话和结构标签，必须加上与主轴对应的产品功能叶子。
6. tags 中是否有与主轴不符的标签？如果有，必须删除。
7. expected_script 末尾不能有独立的导演说明段落（如"整场串联要点：..."），所有导演说明必须写在管家括号块内。
8. 【B3b终极自检】逐条读nl_assertion，问自己"导演能根据这条断言明确勾Pass还是Fail吗？"如果不能，它是无意义的废话断言，必须删除。如果能且它是通用底线约束（如"不得答非所问"），可保留，但必须确保至少有1-2条case专属断言。万能列举（如"打开/关闭/调节/切换等动作之一"）和空泛描述（如"需体现可判定的任务推进结果"）导演无法据此勾Pass/Fail，必须删除。
9. 【功能操作型指令前置检查】冷启动台词是否是功能操作型指令（如"刷新路线""放大地图""切换为详细播报""删除第一个途经点""切歌""暂停"等）？如果是，expected_script 前序轮次是否先构建了对应任务态（如先"导航到XXX"建立导航任务、先"播放XXX"建立播放状态）？途经点删除类是否先添加了≥2个途经点？如果没有前置任务建立，必须补上。
10. 【状态恢复轮检查】case 是否会改变软硬件长期状态（媒体播放/导航任务/车控操作/定时任务）？如果是，expected_script 末尾是否有恢复轮（如"暂停播放""退出导航""关掉空调"）？如果缺恢复轮，必须补上。纯查询类/S2S闲聊/拒识类/记忆类无需恢复轮。
11. 【管家括号块口头反馈检查】expected_script 里所有"管家：（…）"括号块是否含"须明确反馈""须明确告知""须明确说明""须明确回答""须明确回复""须详细说明"等强制口头反馈措辞？如果有，必须删除这些措辞及配套期望台词示例（如"如'已为您调到22度'"），只保留核心动作描述（"须执行XXX"等）和禁止性约束（"不得XXX"）。裁判现在能从车机log核对执行结果，不强制助手口头详细反馈。
12. 【地址真实性检查】case 中出现的所有地址/地名/地标/POI 是否真实存在？若出现具体门牌号地址（如"XX路N号"）且不在白名单内，必须替换为白名单地址或改为泛指地点。白名单已验证地址：上海市浦东新区世纪大道100号、上海市黄浦区中山东一路、上海市浦东新区陆家嘴环路1000号、上海市黄浦区南京东路829号、上海市黄浦区南京西路1266号、杭州市西湖区文三路478号。知名地标（不需门牌号）允许使用：上海中心大厦、外滩、浦东机场、虹桥火车站、恒隆广场、杭州西湖等。泛指地点允许使用：公司、家、附近XX、沿途XX。禁止编造任何地址信息。

【打标完整参考依据：vehicle_assistant_case_tagging_guideline.md 全文】
{{vehicle_assistant_case_tagging_guideline.md}}

【原始case】
{{ORIGINAL_CASE}}

【审核反馈】（第{{ROUND}}轮修复）
{{AUDIT_FEEDBACK}}

【台词保留约束——本批为Excel原始query转化case】
user_query_lists[0] 的冷启动台词（即 user_query_lists[0][0].content）是 Excel 原始 query 的逐字记录，**必须原样保留，不得改写**，除非存在以下任一情况才可修改：
1. 台词含占位符（如 XX路、某POI、其他城市的某个POI）→ 必须替换为真实地址/真实POI（符合§2.1.6真实地址原则）
2. 台词明显不通顺或语法错误 → 仅修正语法，保持原意
3. 台词与审核反馈指出的核心问题直接冲突（如台词本身就是闭环缺失的根源）→ 才可改写
expected_script 中「用户：」行的台词也应尽量保留原始说法，仅在与上述3种情况冲突时才改写。
注意：闭环前置原则（§10.0）要求通过对话生产前提条件，这通常意味着**在 expected_script 中补充前置轮次**（如先说"我公司在朝阳门外大街"再说"导航去公司"），而不是改写原始冷启动台词。请优先用"补前置轮次"的方式满足闭环，而非改写已有台词。

【关键要求：必须直接采纳审核反馈中的suggestion】
审核反馈中每条issue都有suggestion字段，里面是具体的改写建议。你必须直接采纳这些建议，不要自己重新发明。特别是nl_assertion的suggestion，直接用suggestion中给出的具体断言替换原有断言，不要改写回通用描述。
特别强调：
- 如果suggestion说"删除该条断言"，你必须删除，不要保留或改写
- 如果suggestion给出了具体的断言文本，直接使用该文本，不要在其中添加"不得答非所问"等通用修饰
- 如果suggestion说"仅保留第X条"，则nl_assertion只保留那一条，其余全部删除
- 【台词保留例外】如果suggestion要求改写user_query_lists[0]的冷启动台词，必须先判断是否符合上方「台词保留约束」的3种例外情况，符合才改，不符合则保留原台词并在expected_script中补前置轮次满足闭环

【修复步骤——严格按此顺序执行】
第一步：逐条处理审核反馈中的每个issue，按suggestion执行修改。
第二步：处理nl_assertion时，先"全部删除"被审核标记为通用/无区分力的断言，再根据suggestion写入新的专属断言。不要在旧断言基础上修改——删干净再写。
第三步：对写好的nl_assertion做"替换测试"：把每条断言中的具体操作对象替换成XX，如果断言仍然通顺则删除该条。
第四步：【强制修复tags】逐条检查审核反馈中涉及D1/D2/D3原则的issue，对tags执行以下操作：
  - 删除审核反馈明确指出"无对应case内容支撑"的标签
  - 删除审核反馈明确指出"与主轴不符"的标签
  - 删除审核反馈明确指出"应为XX而非YY"的标签中的YY，替换为XX
  - 补充审核反馈明确指出"缺少/遗漏"的标签
  - 补充case中涉及但未打标签的核心功能点对应的产品功能叶子标签
  - 确保tags中包含至少1个产品功能类叶子 + 1个通用对话能力类叶子 + 1个结构/难度类叶子
  - 确保评测结果预期标签（可完成/需澄清/应拒绝/应降级处理）只选一个且与case内容一致
  - 【标签替换必须对照审核原则中的标签粒度混淆高频错表】替换标签时，必须对照审核原则D2中的"标签粒度混淆高频错"列表，确保替换后的标签与case内容匹配。常见错误方向：
    * 用户说"风速稳住/别忽大忽小"→风量增减调节（不是直接设定，因为用户没指定档位）
    * 用户说"调到26度"→温度直接设定（不是增减调节，因为用户指定了具体值）
    * 用户说"换个颜色"→氛围灯模式切换（不是开关）
    * 用户说"导航去人民广场"→精确地点直达（不是地标特征找地点）
    * POI检索题（找餐厅/加油站/商场）→不打联网信息查询标签，除非用户要查公网资讯
  重要：tags修复不是可选的，是必须的！如果审核反馈指出标签问题，你必须修改tags字段，不能只改nl_assertion和expected_script而保留原tags不变。
第五步：输出修复后的完整case JSON。

请输出修复后的完整case JSON（不要输出其他内容，不要输出markdown代码块标记）：
'''


class FixedCase(BaseModel):
    fixed_case: dict = Field(..., description="修复后的完整case JSON")


def _format_audit_feedback(audit_result: dict) -> str:
    if audit_result.get("audit_pass", True):
        return "审核通过，无需修复。"
    lines = []
    for i, iss in enumerate(audit_result.get("issues", []), 1):
        lines.append(
            f"{i}. [{iss.get('principle', '?')}] {iss.get('dimension', '?')} "
            f"[{iss.get('severity', '?')}]\n"
            f"   问题：{iss.get('description', '')}\n"
            f"   建议：{iss.get('suggestion', '')}"
        )
    return "\n".join(lines)


async def audit_case(case: dict) -> dict:
    tag_validation_info = _build_tag_validation_info(case.get("tags", []), case)
    prompt = load_and_assemble_prompt(json.dumps(case, ensure_ascii=False), tag_validation_info)
    result = await allm_output(
        prompt,
        output_type=CaseAudit,
        model=ModelName.DOUBAO_SEED_2_1_TURBO_260628,
        temperature=0.0
    )
    audit = result.output
    return {
        "id": case.get("id"),
        "case_id": case.get("case_id"),
        "audit_pass": audit.audit_pass,
        "issues": [iss.model_dump() for iss in audit.issues],
        "summary": audit.summary
    }


async def fix_case_once(current_case: dict, audit_result: dict, round_num: int) -> dict:
    guideline_text = _load_guideline()
    tag_validation_info = _build_tag_validation_info(current_case.get("tags", []), current_case)
    audit_principles = _merge_audit_principles(tag_validation_info)
    prompt = FIX_PROMPT_TEMPLATE
    prompt = prompt.replace("{{CASE_AUDIT_PRINCIPLES}}", audit_principles)
    prompt = prompt.replace("{{vehicle_assistant_case_tagging_guideline.md}}", guideline_text)
    prompt = prompt.replace("{{ORIGINAL_CASE}}", json.dumps(current_case, ensure_ascii=False, indent=2))
    prompt = prompt.replace("{{AUDIT_FEEDBACK}}", _format_audit_feedback(audit_result))
    prompt = prompt.replace("{{ROUND}}", str(round_num))

    result = await allm_output(
        prompt,
        output_type=FixedCase,
        model=ModelName.DOUBAO_SEED_2_1_TURBO_260628,
        temperature=0.0
    )
    fixed = result.output.fixed_case
    # 兜底：修复 LLM 常会误删 expected_script 开头的重试先导段，必须补回
    fixed = _apply_preamble_safeguard(fixed)
    return fixed


async def fix_case_loop(original_case: dict, initial_audit: Optional[dict] = None, max_rounds: int = MAX_FIX_ROUNDS) -> tuple[dict, list[dict]]:
    if initial_audit is None:
        print("  第0轮：审核原始case...")
        initial_audit = await audit_case(original_case)
        if initial_audit.get("audit_pass", True):
            print("  原始case已通过审核，无需修复。")
            return original_case, [initial_audit]
        print(f"  原始case审核未通过，共 {len(initial_audit.get('issues', []))} 个问题：")
    else:
        if initial_audit.get("audit_pass", True):
            print("  原始case已通过审核，无需修复。")
            return original_case, [initial_audit]
        print(f"  使用已有审核结果，共 {len(initial_audit.get('issues', []))} 个问题：")

    for iss in initial_audit.get("issues", []):
        print(f"    [{iss.get('principle')}] {iss.get('dimension')} - {iss.get('description', '')[:60]}")

    current_case = original_case
    current_audit = initial_audit
    audit_history = [initial_audit]

    for round_num in range(1, max_rounds + 1):
        print(f"\n  第{round_num}轮修复...")
        fixed_case = await fix_case_once(current_case, current_audit, round_num)

        fixed_case["id"] = original_case.get("id", "")
        fixed_case["case_id"] = original_case.get("case_id", "")
        # 兜底：确保修复后 expected_script 仍以重试先导段开头（fix_case_once 内部已有兜底，这里双保险）
        fixed_case = _apply_preamble_safeguard(fixed_case)

        print(f"  第{round_num}轮审核修复后的case...")
        new_audit = await audit_case(fixed_case)
        audit_history.append(new_audit)

        if new_audit.get("audit_pass", True):
            print(f"  [通过] 第{round_num}轮修复后审核通过！")
            return fixed_case, audit_history
        else:
            issue_count = len(new_audit.get("issues", []))
            print(f"  [未通过] 第{round_num}轮修复后仍有 {issue_count} 个问题：")
            for iss in new_audit.get("issues", []):
                print(f"    [{iss.get('principle')}] {iss.get('dimension')} - {iss.get('description', '')[:60]}")
            current_case = fixed_case
            current_audit = new_audit

    print(f"\n  [警告] 达到最大修复轮数({max_rounds})，仍未通过审核。")
    return current_case, audit_history


async def main():
    parser = argparse.ArgumentParser(description="根据审核反馈修复case")
    parser.add_argument("--project", default="general_vehicle_assistant", help="项目名（默认 general_vehicle_assistant）")
    parser.add_argument("--ids", nargs="+", help="指定case id，如 composite-422")
    parser.add_argument("--id-range", nargs=2, type=int, metavar=("LO", "HI"), help="id数字范围")
    parser.add_argument("--tags", nargs="+", help="按标签过滤")
    parser.add_argument("--all", action="store_true", help="修复全部case")
    parser.add_argument("--from-fail", help="从审核fail文件中读取case id进行修复")
    parser.add_argument("--output", help="输出文件路径")
    parser.add_argument("--max-rounds", type=int, default=MAX_FIX_ROUNDS, help="最大修复轮数")
    parser.add_argument("--concurrent", type=int, default=5, help="并发修复数")
    parser.add_argument("--limit", type=int, default=0, help="最多修复N条case（0=不限）")
    args = parser.parse_args()

    max_rounds = args.max_rounds
    project_name = args.project

    # 优先 vehicle_assistant_cases.json，不存在则回退 vehicle_assistant_leaf_cases.json
    cases_file = PROJECT_ROOT / "artifacts" / "projects" / project_name / "cases" / "vehicle_assistant_cases.json"
    if not cases_file.exists():
        cases_file = PROJECT_ROOT / "artifacts" / "projects" / project_name / "vehicle_assistant_leaf_cases.json"

    if args.from_fail:
        fail_path = Path(args.from_fail)
        fail_data = json.loads(fail_path.read_text(encoding="utf-8"))
        fail_ids = [r.get("id") for r in fail_data if r.get("id") and not r.get("audit_pass", True)]
        audit_map = {r.get("id"): r for r in fail_data if r.get("id") and not r.get("audit_pass", True)}
        data = json.loads(cases_file.read_text(encoding="utf-8"))
        id_set = set(fail_ids)
        cases = [c for c in data if c.get("id") in id_set]
        print(f"从fail文件读取 {len(fail_ids)} 个未通过id，匹配到 {len(cases)} 条case（跳过初始审核，直接使用已有审核结果）")
    else:
        data = json.loads(cases_file.read_text(encoding="utf-8"))
        cases = _filter_cases(data, args)
        audit_map = {}

    if not cases:
        print("没有匹配的case")
        return

    if args.limit > 0:
        cases = cases[:args.limit]

    print(f"待修复 {len(cases)} 条case，并发: {args.concurrent}，最大修复轮数: {max_rounds}")

    sem = asyncio.Semaphore(args.concurrent)
    done_count = 0
    pass_count = 0
    t_start = time.monotonic()

    async def _fix_one(case):
        nonlocal done_count, pass_count
        cid = case.get("id", "?")
        case_name = case.get("case_id", "?")
        async with sem:
            try:
                initial_audit = audit_map.get(cid)
                fixed_case, audit_history = await fix_case_loop(case, initial_audit=initial_audit, max_rounds=max_rounds)
                final_pass = audit_history[-1].get("audit_pass", False) if audit_history else False
                done_count += 1
                if final_pass:
                    pass_count += 1
                elapsed = time.monotonic() - t_start
                avg = elapsed / done_count if done_count else 0
                eta = avg * (len(cases) - done_count)
                status = "通过" if final_pass else "未通过"
                print(f"  [{done_count}/{len(cases)}] [{cid}] {status} | "
                      f"通过率 {pass_count}/{done_count} ({pass_count/done_count*100:.1f}%) | "
                      f"已用 {_fmt_duration(elapsed)} 预计剩余 {_fmt_duration(eta)}")
                return {
                    "original_id": cid,
                    "original_case_id": case_name,
                    "fixed_case": fixed_case,
                    "audit_rounds": len(audit_history),
                    "final_pass": final_pass,
                    "issues_if_failed": audit_history[-1].get("issues", []) if not final_pass else []
                }
            except Exception as e:
                done_count += 1
                print(f"  [{done_count}/{len(cases)}] [{cid}] 异常: {str(e)[:80]}")
                return {
                    "original_id": cid,
                    "original_case_id": case_name,
                    "fixed_case": case,
                    "audit_rounds": 0,
                    "final_pass": False,
                    "error": str(e)
                }

    all_fixed = await asyncio.gather(*[_fix_one(c) for c in cases])

    if args.output:
        out_path = Path(args.output)
    else:
        from datetime import datetime
        out_path = Path(__file__).resolve().parent / f"fixed_cases_{datetime.now():%Y%m%d_%H%M%S}.json"
    out_path.write_text(json.dumps(all_fixed, ensure_ascii=False, indent=2), encoding="utf-8")

    fixed_pass = [f for f in all_fixed if f.get("final_pass")]
    fixed_fail = [f for f in all_fixed if not f.get("final_pass")]
    pass_path = out_path.with_name(out_path.stem + "_pass.json")
    fail_path = out_path.with_name(out_path.stem + "_fail.json")
    pass_path.write_text(json.dumps(fixed_pass, ensure_ascii=False, indent=2), encoding="utf-8")
    fail_path.write_text(json.dumps(fixed_fail, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n\n{'='*60}")
    print(f"修复汇总")
    print(f"{'='*60}")
    total = len(all_fixed)
    passed = len(fixed_pass)
    print(f"总case数: {total}")
    print(f"修复后通过审核: {passed} ({passed/total*100:.1f}%)" if total else "总case数: 0")
    print(f"修复后仍未通过: {total - passed}")

    print(f"\n结果已写入:")
    print(f"  全量: {out_path} ({total} 条)")
    print(f"  修复通过: {pass_path} ({len(fixed_pass)} 条)")
    print(f"  修复未通过: {fail_path} ({len(fixed_fail)} 条)")


if __name__ == "__main__":
    asyncio.run(main())
