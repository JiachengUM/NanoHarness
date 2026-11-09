from typing import override

from projects.hwhms.car_a.core import IntentClassifier, ClsResult
from projects.hwhms.common.category import Category


class IntentClassifierNew(IntentClassifier):
    def __init__(self):
        super().__init__()

        # 这里可以修改任意数据成员，例如

        self.llm_params["model"] = "a new model"
        '''修改model'''

        self.car_control_intent.examples.append("打开天窗")
        '''修改意图类别的定义'''

        self.new_intent_catetory = Category(name="新意图类别", description="新意图类别的定义", examples=["新意图类别的示例"])
        '''添加新的意图类别'''


    @override
    async def run(self, query: str, output_structure: bool = False) -> ClsResult | str:
        return await super().run(query, output_structure)


def compare_and_validate():
    classifier = IntentClassifier()
    classifier_new = IntentClassifierNew()

    # step 1: 读取想要测试的数据，通常不是完整的测试集，而是“想要对比的部分，这个实验的改动可能影响的部分”。
    # 例如，仅仅修改了car_control_intent的定义，


    # step 2: 运行classifier, classifier_new, 获取两组结果。


    # step 3: 运行cls_analyze的对比结果工具，分析这个改动的效果：


    # step 4.1: 这个改动如果明显有效，在自己的实验branch上集成到core.py。找wei yichen review code。
    # 运行run_test中的整体测试。如果依然没问题，merge到主分支。

    # step 4.2: 明显不好。不管它。

    # step 4.3: 有好有坏。



if __name__ == "__main__":
    compare_and_validate()
