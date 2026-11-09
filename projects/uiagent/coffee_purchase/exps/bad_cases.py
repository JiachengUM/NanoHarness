import asyncio

from projects.uiagent.coffee_purchase.workflow import Workflow
from projects.uiagent.coffee_purchase.workflow_eval import StepData, load_step_dataset
from projects.uiagent.coffee_purchase.datasets import DATASET_ROOT
from projects.uiagent.core import RunResult, JudgeResult, Page
from projects.uiagent.core.visualize import draw_step_result
from projects.uiagent.core.eval import eval_step_batch
from projects.uiagent.core import image_from_path
from nanoai.utils.async_utils import amap


EXP_CONFIGS = [
    {"dataset": "coffee_step3", "id": 50, "priority": 0, "comment": "错别字情况,无需重新搜索"},
    {"dataset": "coffee_step4", "id": 14, "priority": 0, "comment": "不存在的选项需要通过ask_human,不支持点击展开选项区域"}, 
    {"dataset": "coffee_step4", "id": 5,  "priority": 0, "comment": "query只有部分属性时，需要通过ask_human确认其他的属性是否需要选择，不应直接下单。"},
    {"dataset": "coffee_step4", "id": 3,  "priority": 0, "comment": "不存在的选项"},
    {"dataset": "coffee_step4", "id": 17, "priority": 0, "comment": "同一个属性不可选择多个选项"},
    {"dataset": "coffee_step4", "id": 24, "priority": 0, "comment": "已满足选项要求，理应询问用户来确认其他的选项。"},
    {"dataset": "coffee_step4", "id": 30, "priority": 0, "comment": "已满足选项要求，理应询问用户来确认其他的选项。"},

    {"dataset": "coffee_step2", "id": 32, "priority": 1,"comment": "本意是需要进行模糊匹配"},
    {"dataset": "coffee_step2", "id": 41, "priority": 1,"comment": "本意是需要进行模糊匹配"},
    {"dataset": "coffee_step3", "id": 4, "priority": 1,"comment": "直接选择商品"},
    {"dataset": "coffee_step3", "id": 13, "priority": 1,"comment": "随意选择时，可以直接选。不询问用户。"},
    {"dataset": "coffee_step3", "id": 14, "priority": 1,"comment": "需要模糊匹配时，直接去选"},
    {"dataset": "coffee_step3", "id": 15, "priority": 1,"comment": "需要模糊匹配时，直接去选"},
    {"dataset": "coffee_step3", "id": 19, "priority": 1,"comment": "无关键字，需要模糊匹配时，"},
    {"dataset": "coffee_step3", "id": 23, "priority": 1,"comment": "需要模糊匹配，直接去选"},
    {"dataset": "coffee_step3", "id": 26, "priority": 1,"comment": "需要模糊匹配，直接去选"},
    {"dataset": "coffee_step3", "id": 28, "priority": 1,"comment": "需要模糊匹配，直接去选"},
    {"dataset": "coffee_step3", "id": 37, "priority": 1,"comment": "需要模糊匹配，直接去选"},
    {"dataset": "coffee_step3", "id": 43, "priority": 1,"comment": "有遮盖，点击中间，避免点击失败"},
    {"dataset": "coffee_step3", "id": 47, "priority": 1,"comment": "有遮盖，点击中间，避免点击失败"},
    {"dataset": "coffee_step3", "id": 54, "priority": 1,"comment": "价格维度的识别，最便宜的，最优惠的，最贵的，因为会有原价，优惠价展示"},
    {"dataset": "coffee_step4", "id": 4, "priority": 1,"comment": "模糊商品规格选择"},
    {"dataset": "coffee_step4", "id": 12, "priority": 1,"comment": "query有歧义,以选属性维度为高优先级"},
    {"dataset": "coffee_step4", "id": 21, "priority": 1,"comment": "模糊的数量如何解决"},
    {"dataset": "coffee_step4", "id": 26, "priority": 1,"comment": "其他的需求，增加换购，"},
    {"dataset": "coffee_step4", "id": 71, "priority": 1,"comment": "小杯。小黑杯，表述不一致"},
    {"dataset": "coffee_step4", "id": 85, "priority": 1,"comment": "冰、少冰表述"},

    {"dataset": "coffee_step2", "id": 14, "priority": 2,"comment": "模糊地址表述"},
    {"dataset": "coffee_step2", "id": 28, "priority": 2,"comment": "地址模糊匹配，尽可能的去匹配到对应的地址"},
    {"dataset": "coffee_step2", "id": 39, "priority": 2,"comment": "地址模糊匹配，尽可能的去匹配到对应的地址"},
    {"dataset": "coffee_step3", "id": 10, "priority": 2,"comment": "部分商品可能是灰色的不可选"},
    {"dataset": "coffee_step3", "id": 16, "priority": 2,"comment": "部分商品可能是灰色的不可选"},
    {"dataset": "coffee_step3", "id": 18, "priority": 2,"comment": "异常模糊，无法确认的需反问"},
    {"dataset": "coffee_step3", "id": 20, "priority": 2,"comment": "价格维度"},
    {"dataset": "coffee_step3", "id": 31, "priority": 2,"comment": "模糊匹配，加价格维度"},
    {"dataset": "coffee_step3", "id": 33, "priority": 2,"comment": "有浮窗遮挡。"},
    {"dataset": "coffee_step3", "id": 34, "priority": 2,"comment": "模糊表述＋不可购买"},
    {"dataset": "coffee_step4", "id": 29, "priority": 2,"comment": "超级换购需求"},
    {"dataset": "coffee_step4", "id": 38, "priority": 2,"comment": "无大杯"},
    {"dataset": "coffee_step4", "id": 40, "priority": 2,"comment": "无小杯"},
    {"dataset": "coffee_step4", "id": 50, "priority": 2,"comment": "不可选择选项+点击"},
    {"dataset": "coffee_step4", "id": 51, "priority": 2,"comment": "多action"},
    {"dataset": "coffee_step4", "id": 53, "priority": 2,"comment": "不可多选"},
    {"dataset": "coffee_step4", "id": 59, "priority": 2,"comment": "要求有点绕口"},
    {"dataset": "coffee_step4", "id": 60, "priority": 2,"comment": "有匹配的关键字。"},
    {"dataset": "coffee_step4", "id": 61, "priority": 2,"comment": "超级换购需求+原商品属性需求"},
    {"dataset": "coffee_step4", "id": 72, "priority": 2,"comment": "不存在选项"},
    {"dataset": "coffee_step4", "id": 74, "priority": 2,"comment": "不存在该选项"},
    {"dataset": "coffee_step4", "id": 82, "priority": 2,"comment": "存在，但不能去点击，应告知用户"},
    {"dataset": "coffee_step4", "id": 84, "priority": 2,"comment": "超级换购需求、存在"},
    {"dataset": "coffee_step4", "id": 88, "priority": 2,"comment": "不存在该选项"},
    {"dataset": "coffee_step4", "id": 90, "priority": 2,"comment": "弯弯绕绕的说法。"},
    {"dataset": "coffee_step4", "id": 91, "priority": 2,"comment": "不存在选项"},
    {"dataset": "coffee_step4", "id": 93, "priority": 2,"comment": "超级换购需求"},

]
class WorkflowNew(Workflow):

    def __init__(self):
        super().__init__()

        self.select_shop_task.note.append("在地点名模糊、错别字等情况下，可以直接去匹配类似的地址点击，而一定不需要去搜索或新建,最差也是询问用户。")
        self.select_shop_task.note.append("个人信息填写时，涉及文本框输入的往往都是先点击对应的文本框，再给出对应的填写内容。如`姓名就方先生`应当有姓名框点击，输入内容`方先生`，以及点击`性别`中的`先生`。")

        # 商品未完全匹配,同音字情形
        self.select_product_task.note.append("在商品名模糊、错别字、部分关键字匹配等情况下，可以直接去匹配类似带有关键字的商品点击，而不能去清空内容重新搜索！")
        self.select_product_task.note.append("确认目标商品后，执行点击动作的时候需要点击对应位置块的中间位置，而不是那个`+`号，因为有可能被遮盖住。")
        self.select_product_task.note.append("用户表示随意选择时，你决定选一个即可。")
        self.select_product_task.note.append("忽略搜索框内的内容，只需要关注商品列表中的商品名称！")
        self.select_product_task.note.append("涉及到按价格维度选商品时，优先依据实付的价格进行选择。") #有待商讨
        self.select_product_task.note.append("部分商品可能是灰色的不可选，此时应告知用户进行修改。")
        self.select_product_task.note.append("若信息太过模糊时，如`蛋糕`这种大类的描述，无法进行关键字匹配时，需去询问用户具体指的是什么商品，顺带加上过滤后的较为合理的商品。")


        self.select_spec_task.page = Page(
            name="瑞幸咖啡小程序选择商品详细规格的页面", 
            description="用户已经确认好了商品，通常包含多个选择按钮，用户可以点击选择不同的商品属性。如果用户指定个别属性为默认选项不用操作时，也是用ask_human动作，去确认其他属性该怎么选；若用户为所有属性提供了明确的值且已勾选时，此时可告知用户当前已选的详细信息，是否直接下单!"
            )
        self.select_spec_task.note.append("当前页面所展示的属性不支持点击展示更多的选项,若没有相应子属性，应告知用户。")
        self.select_spec_task.note.append("同一个属性中只能选择一个选项,如果用户选择多个选项，应告知用户当前不支持多选，需要修改。回复类似如：当前的xx（糖度）不支持多选呢，请您重新选择下。")
        self.select_spec_task.note.append("当前页面所展示的属性多选项时，会自左向右，自上而下进行展示。即除了默认的一个选项，右侧为空时，就表明不支持其他的选项，此时明确告知用户就行。如杯型属性、茶风味、温度，只展示了一个`大杯`或`茉莉花香`或`热`，那么右侧就不再有多余的选项，也就不支持其他的选择。如`冰`、`小杯`")
        self.select_spec_task.note.append("若用户提供的属性由于不存在而无法选中时，此时应告知用户进行修改。")
        self.select_spec_task.note.append("若用户提供的数量不明确且表示随意的意愿时，你需要询问用户具体的数量。")
        self.select_spec_task.note.append("超值换购往往指的是在当前页面的属性选择下方，会提供几个商品，供用户选择。点击商品中间位置即可添加。重点：当前不支持超值换购功能！简短回答即可，无需解释。") # 需商讨属性页是否要支持`增加换购商品`能力
        self.select_spec_task.note.append("部分商品杯型属性部分的表述可能不太一致,本质是一个意思。如：小黑杯-->小杯。") 
        self.select_spec_task.note.append("若有多因素时,100%明确的动作应作为一个action,不能执行的需告知用户，此时是两个动作。而不应该将明确的动作归并到一个中去！") 
        # self.select_spec_task.note.append("若有其他商品的加购意图且商品表述过为模糊，此时可优先进行关键字的模糊匹配去选择超值换购的商品，但无需过问商品的规格。如果实在没有则需告知用户。") 
        # self.select_spec_task.note.append("属性的展示规则，如温度属性的`冰`、`热`、`少冰`等，下方及上方有新的属性（如：杯型、糖）出现时，就代表温度的所有选项都展示了。不会再有更多的关于温度属性的选择了。")



async def run_step_original(step_data: StepData, output_dir: str | None = None, enable_reflect: bool = True) -> tuple[RunResult, JudgeResult | None]:
    """使用原始 Workflow 执行单步"""
    workflow = Workflow(enable_reflect=enable_reflect)
    base64_image, image_format = image_from_path(step_data.image_path)
    result, eval_res = await workflow.run(
        step_data.query, base64_image, image_format, current_step=step_data.step
    )
    if output_dir is not None:
        draw_step_result(step_data, result, eval_res, output_dir)
    return result, eval_res


async def run_step_new(step_data: StepData, output_dir: str | None = None, enable_reflect: bool = True) -> tuple[RunResult, JudgeResult | None]:
    """使用修改后的 WorkflowNew 执行单步"""
    base64_image, image_format = image_from_path(step_data.image_path)
    workflow = WorkflowNew()
    workflow.enable_reflect = enable_reflect
    result, eval_res = await workflow.run(
        step_data.query, base64_image, image_format, current_step=step_data.step
    )
    if output_dir is not None:
        draw_step_result(step_data, result, eval_res, output_dir)
    return result, eval_res


def compare_and_validate():
    """对比原始和修改后的 workflow 效果，这里看的是正确率、错误率"""
    # step 1: 读取想要测试的数据，通常不是完整的测试集，而是“想要对比的部分，这个实验的改动可能影响的部分”。

    for dataset_name in ["coffee_step2", "coffee_step3", "coffee_step4"]:
        dataset_path = DATASET_ROOT.resolve() /f"{dataset_name}"
        all_steps = list(load_step_dataset(dataset_path, StepData))


        # all_steps = [step for step in all_steps if step.priority == 0 ]
        
        # step 2: 运行原始和修改后的 workflow, 获取两组结果。
        # res = eval_step_batch(all_steps, run_step_original, save_image_root=DATASET_ROOT.resolve() / "1107_exps_outputs")
        res_new = eval_step_batch(all_steps, run_step_new, save_image_root=DATASET_ROOT.resolve() / "1110_exps_results_new_1")

        # step 3: 对比结果，分析这个改动的效果：
        # compre res, res_new
        # print("="*60)
        # print("原始 Workflow 结果:")
        # res.print()
        print("="*60)
        print("修改后 Workflow 结果:")
        print(f"dataset_name: {dataset_name}")
        res_new.print()

    # step 4.1: 改动如果明显有效，在自己的实验branch上集成到workflow.py。找wei yichen review code。通过后merge到主分支。

    # step 4.2: 明显不好。不管它。

    # step 4.3: 有好有坏。最难的情况, case by case分析。


def compare_result(config: dict | None = None):
    """对比原始和修改后的 workflow ，看模型输出。"""
   
    # step 1: 读取数据
    dataset_path = DATASET_ROOT.resolve() / config["dataset"]
    all_steps = list(load_step_dataset(dataset_path, StepData))[config["id"]-1]
    all_steps = all_steps if isinstance(all_steps, list) else [all_steps]

    
    output_path_orig = DATASET_ROOT.resolve() / "exps_outputs_orig"/str(config["priority"])
    output_path_new = DATASET_ROOT.resolve() / "exps_results_new"/str(config["priority"])

    print(f"###############【备注】: {config['comment']}###################")
    for i, step_data in enumerate(all_steps, 1):
        print(f"\n[样本 {i}/{len(all_steps)}] ID: {step_data.id}, Query: {step_data.query}")
        
        # 运行原始版本
        result_orig, judge_orig = asyncio.run(run_step_original(step_data, output_path_orig, enable_reflect=False))
        
        # 运行新版本
        result_new, judge_new = asyncio.run(run_step_new(step_data, output_path_new, enable_reflect=False))

        print("="*60)
        print("原始 Workflow 模型输出及评判:")
        print(f"模型思考：{result_orig.thought}\n动作：{result_orig.actions}\n评判：{judge_orig}")
        print("="*60)
        print("修改后 Workflow 模型输出及评判:")
        print(f"模型思考：{result_new.thought}\n动作：{result_new.actions}\n评判：{judge_new}")
        print("="*60)


if __name__ == "__main__":
    # 实测 step4 跑完评估偶尔会报错。不常见，但存在。
    # compare_and_validate()
    
    compare_result(EXP_CONFIGS[-1])  # 只跑最后一个
    # print("="*60)
    # 逐bad_case推理。遍历EXP_CONFIGS,方便比对
    # for bad_case in EXP_CONFIGS:
    #     compare_result(bad_case)
    #     print("="*60)



