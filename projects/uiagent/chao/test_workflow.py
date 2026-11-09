from uitars import uitars_call_with_context
from uitars import uitars_call_with_prompt
from doubao import doubao_text_call
import prompt
import json
import pytest

@pytest.mark.parametrize("image_path, query, prompt", [
    ("../datasets/lssf/001.png", "点击搜索框", prompt.UI_TARS_PROMPT_WITH_BUTTON_NAME),
    ("../datasets/lssf/002.png", "在输入框输入“庐上帅府”，然后点击搜索", prompt.UI_TARS_PROMPT_WITH_BUTTON_NAME),
    ("../datasets/lssf/003.png", "在搜索结果中选择第一个餐厅点击", prompt.UI_TARS_PROMPT_WITH_BUTTON_NAME),
    ("../datasets/lssf/004.png", "点击AI帮订按钮", prompt.UI_TARS_PROMPT_WITH_BUTTON_NAME),
    ("../datasets/lssf/005.png", "点击明天", prompt.UI_TARS_PROMPT_WITH_BUTTON_NAME),
    ("../datasets/lssf/006.png", "点击19:00", prompt.UI_TARS_PROMPT_WITH_BUTTON_NAME),
    ("../datasets/lssf/007.png", "点击8人", prompt.UI_TARS_PROMPT_WITH_BUTTON_NAME),
    ("../datasets/lssf/008.png", "点击下一步", prompt.UI_TARS_PROMPT_WITH_BUTTON_NAME),
    ("../datasets/lssf/009.png", "点击确认订座", prompt.UI_TARS_PROMPT_WITH_BUTTON_NAME),
])
def test_uitars_scroll_no_context(image_path: str, query: str, prompt: str):
    """

    """
    print(f"=== 开始-{image_path} ===")

    try:
        result = uitars_call_with_prompt(image_path, query, prompt)
        if result['success']:
            # print(json.dumps(result, indent=4, ensure_ascii=False))
            print(result['content'])

    except Exception as e:
        print(f"❌ 测试异常: {e}")

    return result

@pytest.mark.parametrize("image_path, query, prompt", [
    # ("../datasets/lssf/001.png", "帮我在庐上帅府，订一个明天19:008个人的包间", prompt.UI_TARS_PROMPT_WITH_BUTTON_NAME),
    ("../datasets/lssf/002.png", "帮我在庐上帅府，订一个明天19:008个人的包间", prompt.UI_TARS_PROMPT_WITH_BUTTON_NAME),
    # ("../datasets/lssf/003.png", "在搜索结果中选择第一个餐厅点击", prompt.UI_TARS_PROMPT_WITH_BUTTON_NAME),
    # ("../datasets/lssf/004.png", "点击AI帮订按钮", prompt.UI_TARS_PROMPT_WITH_BUTTON_NAME),
    # ("../datasets/lssf/005.png", "点击明天", prompt.UI_TARS_PROMPT_WITH_BUTTON_NAME),
    # ("../datasets/lssf/006.png", "点击19:00", prompt.UI_TARS_PROMPT_WITH_BUTTON_NAME),
    # ("../datasets/lssf/007.png", "点击8人", prompt.UI_TARS_PROMPT_WITH_BUTTON_NAME),
    # ("../datasets/lssf/008.png", "点击下一步", prompt.UI_TARS_PROMPT_WITH_BUTTON_NAME),
    # ("../datasets/lssf/009.png", "点击确认订座", prompt.UI_TARS_PROMPT_WITH_BUTTON_NAME),
])
def test_uitars_scroll_no_context2(image_path: str, query: str, prompt: str):
    """

    """
    print(f"=== 开始-{image_path} ===")

    try:
        result = uitars_call_with_prompt(image_path, query, prompt)
        if result['success']:
            # print(json.dumps(result, indent=4, ensure_ascii=False))
            print(result['content'])

    except Exception as e:
        print(f"❌ 测试异常: {e}")

    return result

def test_instruction_split():
    try:
        query = "帮我在庐上帅府，订一个明天19:00 8个人的包间"
        result = doubao_text_call(query, prompt.INSTRUCTION_DECOMPOSITION)
        if result['success']:
            # print(json.dumps(result, indent=4, ensure_ascii=False))
            print(result['content'])
            instructions = json.loads(result['content'])
            for inst in instructions:
                print(inst)

    except Exception as e:
        print(f"❌ 测试异常: {e}")
    return result

def test_instruction_split2():
    query = "帮我在刘一手重庆火锅订一个今天19:00 4个人的座"
    # 使用模型拆解query
    instructions = instruction_split(query, prompt.INSTRUCTION_DECOMPOSITION2)
    print(instructions)

def instruction_split(query: str, prompt: str):
    '''
    用户指令通过大模型拆解为一个一个的子任务
    '''
    result = doubao_text_call(query, prompt)
    if result['success']:
        print(result['content'])
        instructions = json.loads(result['content'])
        return instructions
    else:
        print(json.dumps(result, indent=4, ensure_ascii=False))
        return []
def test_workflow1():
    '''
    query、初始图片
    query:帮我在庐上帅府，订一个明天19:008个人的包间
    思路：
    1、先将用户query拆解成一个一个的单步指令(使用大语言模型)
    2、zaiground_truth.json中把流程标注出来(主要标页面对应的校验动作、button_name、下一个页面)
    3、给出第一个页面和query
    这样整个流程就能按标注的数据进行校验跑的准确性，通过校验后再继续执行下一个页面，直至最终结束(end=true)
    '''
    query = "帮我在庐上帅府，订一个明天19:00 8个人的包间"
    #使用模型拆解query
    instructions = instruction_split(query, prompt.INSTRUCTION_DECOMPOSITION)
    # instructions = [
    #     "点击搜索框",
    #     "在输入框输入“庐上帅府”，然后点击搜索",
    #     "在搜索结果中选择第一个餐厅点击",
    #     "点击AI帮订按钮",
    #     "点击明天",
    #     "点击19:00",
    #     "点击8人",
    #     "点击下一步",
    #     "点击确认订座"
    # ]

    #获取ground_truth
    with open("../datasets/lssf/lssf_ground_truth.json", "r", encoding="utf-8") as f:
        ground_truth_data = json.load(f)
    ground_truth_map = {item['img_path']: item['check'] for item in ground_truth_data}

    first_pic = "../datasets/lssf/001.png"
    round = 1
    image_path = first_pic
    while True:
        #报错、校验失败、end=true的情况下退出循环
        try:
            instruction = instructions[round-1]
            result = uitars_call_with_prompt(image_path, instruction, prompt.UI_TARS_PROMPT_WITH_BUTTON_NAME)
            if result['success']:

                check_data = ground_truth_map.get(image_path)
                model_res = json.loads(result['content'])
                actions = model_res.get('actions')
                check_res = False
                for action_info in actions:
                    #检查动作和btn 名是否和ground truth一致
                    if action_info.get('action') == check_data.get('action') and check_data.get('button_name') in action_info.get('button_name'):
                        check_res = True
                if check_res:
                    print(f"✅ 测试通过: {image_path}")
                    print(result['content'])
                    if check_data.get('end'):
                        print(f"✅ 流程执行结束")
                        break
                    else:
                        round += 1
                        image_path = check_data.get('next_page')
                else:
                    print(f"❌ 测试失败: {image_path}")
                    print(result['content'])
                    break
            else:
                print(json.dumps(result, indent=4, ensure_ascii=False))
                break

        except Exception as e:
            print(f"❌ 测试异常: {e}")
            break


    return ""