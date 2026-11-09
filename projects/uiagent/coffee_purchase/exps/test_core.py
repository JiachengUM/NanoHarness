import pytest
import asyncio

from nanoai.model.vlm import avlm, image_from_path

from projects.uiagent.core.action import parse_action

from projects.uiagent.coffee_purchase.workflow import EStep, Workflow
from projects.uiagent.coffee_purchase.datasets import DATASET_ROOT
from projects.uiagent.utils.utils import parse_thought_and_action_content


image_root = DATASET_ROOT / "coffee" / "images"

query_list = [
    # ("单份奶，少少甜就可以",  str(image_root / "商品属性页_002.jpg"), EStep.SELECT_SPEC),
    # ("默认值就可以",  str(image_root / "商品属性页_002.jpg"), EStep.SELECT_SPEC),# 测试 ask 动作
    # ("单份奶，不另外加糖",  str(image_root / "商品属性页_002.jpg"), EStep.SELECT_SPEC),# 测试 ask_human 动作
    # ("单份奶，不另外加糖，两倍，要冰的",  str(image_root / "商品属性页_002.jpg"), EStep.SELECT_SPEC),# 测试 多action 动作
    # ("双份奶",  str(image_root / "商品属性页_002.jpg"), EStep.SELECT_SPEC),
    # ("搜索平金中心1号楼",  str(image_root / "选门店_001.jpg"), EStep.SELECT_SHOP),
    # ("单份奶,少少甜,冰的就可以",  str(image_root / "商品属性页_002.jpg"), EStep.SELECT_SPEC),
    ("搜索上海七宝店",  str(image_root / "选门店_001.jpg"), EStep.SELECT_SHOP),

]

@pytest.mark.parametrize("query, image_path, step", query_list)
def test_get_raw_model_output(query: str,image_path: str, step: EStep):
    """测试获取大模型的原始输出，不进行解析"""
    # 创建 workflow 实例以获取 client 和 model
    workflow = Workflow(enable_reflect=False)
    
    # 获取当前步骤的 prompt
    prompt = workflow.ui_tasks[step].as_prompt(query)
    
    # 直接调用 avlm 获取原始输出
    base64_image, image_format = image_from_path(image_path)
    response = asyncio.run(
        avlm(prompt, base64_image, image_format, client=workflow.client, model=workflow.model)
    )
    print(f"\n{'='*60}")
    print(f"query: {query}")
    print(f"prompt: {prompt}")
    print(f"{'='*60}")
    print(f"原始模型输出:\n{response}")

    try:
        # 解析thought,action_content
        thought, action_content = parse_thought_and_action_content(response)
        print(f"{'='*60}\n")
        print(f"解析后的thought --> {thought}\naction --> {action_content}")
        # 优化后的parse_action
        actions = parse_action(action_content)
        print(f"解析后的actions --> {actions}")

    except Exception as e:
        print(f"{'='*60}\n")
        print(f"解析失败: {e}")
        # return None



invalid_character = ['无需额外动作（各默认属性已选中，数量正确）)',
    '无需额外操作，当前页面各属性及数量均为默认状态。)',
    '无需额外操作，默认选项已全部确认。)',
    '无需额外操作（当前页面默认选项已全部符合要求，数量也正确）)',
    '无需额外点击操作（默认选项已满足任务要求，杯型、温度、糖度、气泡及数量均为默认正确状态）)',
    ]


action_content_cases: list[tuple[str, str]] = [
("click(start_box='(941,859)')\n\n\nclick(start_box='(941,859)')\nclick(start_box='(941,859)')", "多个换行符"),
("click(start_box='(531,565)')；click(start_box='(531,675)')", "中文分号"),
("click(start_box='(941,842)')\n\nclick(start_box='(528,810)')",  "多换行情况"),
("click(start_box='(914,486)')\n\ntype(content='平金中心1号楼')", "多类型动作"),
("ask_human(content='无需额外操作，默认选项已全部确认。)')", "新增ask_human"),
("scroll(start_box='(264,482)', direction='left')\nclick(start_box='(185,482)')", "假设滑动后左边出现小杯，此处坐标需根据实际，但逻辑是滑动杯型区域找小杯并点击。"),
("click(start_box='(265,628)')\nclick(start_box='(534,737)')", "单换行情况"),
("（注：实际操作中，若点击杯型区域后有弹窗或滑动展开选项，需进一步选择小杯。但根据当前截图，杯型显 示为“小黑杯”，推测点击该区域可展开杯型选择，故先点击杯型区域，再滑动查看小杯选项。）)", "没有action"),
]


# @pytest.mark.parametrize("action_and_comment", invalid_character) # 已通过调整输出格式规避这种情况
@pytest.mark.parametrize("action_and_comment", action_content_cases)
def test_parse_action_case_2(action_and_comment: tuple[str, str]):
    actions = parse_action(action_and_comment[0])
    print(f"\ncomment: {action_and_comment[1]}, query: {action_and_comment[0]}\n解析得到的actions: {actions}\n")


RUN_PYTEST = False


def main():
    #for query, image_path, step in query_list:  
        #    test_get_raw_model_output(query, image_path, step)
        
    for action_and_comment in action_content_cases:
        try:
            test_parse_action_case_2(action_and_comment)
        except Exception as e:
            print(f"error: {e} for action_and_comment: {action_and_comment}")



if __name__ == "__main__":
    if RUN_PYTEST:
        pytest.main([__file__, "-v", "-s"])
    else:
        main()
