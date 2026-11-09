# 将特定格式的excel转化成约定好格式的工作流数据集


def convert_excel_to_workflow_dataset(excel_path: str, output_dir: str):
    """将特定格式的excel转化成约定好格式的工作流数据集并保存"""
    # 读取excel文件

    # 数据集schema
    # id, step(这个在excel里没有，需要加，每一步加一个step，人工标注), query, image_path,xml_path(有些步骤需要，不需要的话为空), tags([tag1,tag2,tag3]，现在一级二级三级全部拍扁，如果某一步是反问，那么加上nl_task标签，其他都加上ui_task标签),comment（备注，现在没有就空着）

    # 每个数据集生成一个json dataset profile，相当于数据集简述
    dataset_profile = {
        "name": "捷运停车系统",
        "description": "捷运停车系统的工作流数据集",
        "version": "1.0",
        "total_cases": 100,
        "total_tags":{
            "P0":["tags1","tags2"],
            "P1":["tags3","tags4"],
            "UNKNOWN":["tags5","tags6"]
        },  # 所有标签，因为不一定所有标签都在数据集里出现过
        "example_case": {
            "id": 1,
            "step": 1,
            "query": "你好",
            "image_path": "orders/order_001.jpg",
            "xml_path": "orders/order_001.xml",
            "tags": ["nl_task", "多步骤任务", "车牌号确定，首页有车牌", "无缴费订单情况"],
            "comment": "",
        }
    }
    # 一个单步测试数据集是一个目录及其内部约定的子目录和文件组成。子目录有image,xml,子文件有data.jsonl, dataset_profile.json两个文件
    # 我们将写一个简单的评测脚本，实现如下功能：
    
    def test_batch_eval():
        '''测试单步评估'''
        # 1、load_data_set
        steps = load_step_dataset(DATASET_ROOT / "coffee_step2", StepDataCoffeePurchase)
        # import random
        # steps = random.sample(steps, 3)
        for step in steps:
            print(f"step: {step}")
        output_dir = str(DATASET_ROOT / "new_workflow_results")
        # 2、使用现有的eval_step_batch批量运行（会在save_image_root产出根据大模型输出的动作渲染的图片以及大模型评判结果辅助人工查看结果）
        eval_result = eval_step_batch(steps, Workflow, save_image_root=output_dir)
        # 3、生成评估报告，包含——所有标签——的——各自的——正确率，失败率（失败不是错误而是未能成功运行出结果的比率），case数——
        # TODO
    }
    # 
