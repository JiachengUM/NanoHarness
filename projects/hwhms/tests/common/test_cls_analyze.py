import pytest

from projects.hwhms.common.cls_analyze import cls_evaluate, cls_evaluate_twice, ResultState, ClsMetric


class TestClsEvaluate:
    """测试 cls_evaluate 函数"""

    def test_basic_functionality(self):
        """测试基本功能：正确、错误、混合预测"""
        # 测试全部正确
        pred: list[int | None] = [0, 1, 2, 0, 1]
        gt = [0, 1, 2, 0, 1]
        result = cls_evaluate(pred, gt, num_classes=3)
        assert result.accuracy == 1.0
        assert result.states == [ResultState.CORRECT] * 5
        assert result.conf_mat == [[2, 0, 0], [0, 2, 0], [0, 0, 1]]
        recalls, precisions = result.recall_and_precision
        assert recalls == [1.0, 1.0, 1.0]  # 所有类别召回率都是1.0
        assert precisions == [1.0, 1.0, 1.0]  # 所有类别精确率都是1.0

        # 测试全部错误
        pred = [1, 0, 0, 1, 0]
        gt = [0, 1, 2, 0, 1]
        result = cls_evaluate(pred, gt, num_classes=3)
        assert result.accuracy == 0.0
        assert result.states == [ResultState.WRONG] * 5
        assert result.conf_mat == [[0, 2, 0], [2, 0, 0], [1, 0, 0]]
        recalls, precisions = result.recall_and_precision
        assert recalls == [0.0, 0.0, 0.0]  # 所有类别召回率都是0.0
        assert precisions == [0.0, 0.0, 0.0]  # 所有类别精确率都是0.0

        # 测试混合情况
        pred = [0, 1, 2, 0, 1]
        gt = [0, 1, 2, 1, 1]
        result = cls_evaluate(pred, gt, num_classes=3)
        assert result.accuracy == 0.8  # 4/5 正确
        assert result.states == [
            ResultState.CORRECT, ResultState.CORRECT, ResultState.CORRECT,
            ResultState.WRONG, ResultState.CORRECT
        ]
        assert result.conf_mat == [[1, 0, 0], [1, 2, 0], [0, 0, 1]]
        recalls, precisions = result.recall_and_precision
        assert recalls == [1.0, 2/3, 1.0]  # 类别1的召回率是2/3
        assert precisions == [0.5, 1.0, 1.0]  # 类别0的精确率是0.5

    def test_none_predictions(self):
        """测试None值处理"""
        # 测试包含None值
        pred: list[int | None] = [0, None, 2, 0, 1]
        gt = [0, 1, 2, 1, 1]
        result = cls_evaluate(pred, gt, num_classes=3)
        assert result.accuracy == 0.6  # 3/5 正确
        assert result.states == [
            ResultState.CORRECT, ResultState.NO_OUTPUT, ResultState.CORRECT,
            ResultState.WRONG, ResultState.CORRECT
        ]
        assert result.conf_mat == [[1, 0, 0], [1, 1, 0], [0, 0, 1]]

        # 测试全部None
        pred = [None, None, None]
        gt = [0, 1, 2]
        result = cls_evaluate(pred, gt, num_classes=3)
        assert result.accuracy == 0.0
        assert result.states == [ResultState.NO_OUTPUT] * 3
        assert result.conf_mat == [[0, 0, 0], [0, 0, 0], [0, 0, 0]]

    def test_edge_cases(self):
        # 单类别
        pred_single: list[int | None] = [0, 0, 0]
        gt_single = [0, 0, 0]
        result = cls_evaluate(pred_single, gt_single, num_classes=1)
        assert result.accuracy == 1.0
        assert result.states == [ResultState.CORRECT] * 3
        assert result.conf_mat == [[3]]

        # 长度不匹配错误
        pred_mismatch: list[int | None] = [0, 1]
        gt_mismatch = [0, 1, 2]
        with pytest.raises(ValueError, match="预测结果和真实标签长度不匹配"):
            cls_evaluate(pred_mismatch, gt_mismatch, num_classes=3)
            

    def test_special_labels_and_types(self):
        """测试特殊标签和类型"""
        # 测试标准标签 [0, 1, 2]
        pred_standard: list[int | None] = [0, 1, 2]
        gt_standard = [0, 1, 2]
        result = cls_evaluate(pred_standard, gt_standard, num_classes=3)
        assert result.accuracy == 1.0
        assert result.states == [ResultState.CORRECT] * 3
        assert result.conf_mat == [[1, 0, 0], [0, 1, 0], [0, 0, 1]]

        # 测试二分类
        pred_binary: list[int | None] = [0, 1, 0, 1]
        gt_binary = [0, 1, 0, 1]
        result = cls_evaluate(pred_binary, gt_binary, num_classes=2)
        assert result.accuracy == 1.0
        assert result.states == [ResultState.CORRECT] * 4
        assert result.conf_mat == [[2, 0], [0, 2]]

        # 测试大型混淆矩阵
        pred_large: list[int | None] = [0, 1, 2, 3, 4, 5]
        gt_large = [0, 1, 2, 3, 4, 5]
        result = cls_evaluate(pred_large, gt_large, num_classes=6)
        assert result.accuracy == 1.0
        assert result.states == [ResultState.CORRECT] * 6
        assert len(result.conf_mat) == 6
        assert all(len(row) == 6 for row in result.conf_mat)

        # 返回类型验证
        assert isinstance(result, ClsMetric)
        assert isinstance(result.accuracy, float)
        assert isinstance(result.conf_mat, list)
        assert isinstance(result.states, list)
        assert all(isinstance(stat, ResultState) for stat in result.states)


class TestClsEvaluateTwice:
    """测试 cls_evaluate_twice 函数"""

    def test_basic_functionality(self):
        """测试基本功能：两次预测结果相同的情况"""
        # 测试两次预测都正确且相同
        pred0: list[int | None] = [0, 1, 2, 0, 1]
        pred1: list[int | None] = [0, 1, 2, 0, 1]
        gt = [0, 1, 2, 0, 1]
        result = cls_evaluate_twice(pred0, pred1, gt, num_classes=3)
        assert result.accuracy == 1.0
        assert result.states == [ResultState.CORRECT] * 5
        assert result.conf_mat == [[2, 0, 0], [0, 2, 0], [0, 0, 1]]
        recalls, precisions = result.recall_and_precision
        assert recalls == [1.0, 1.0, 1.0]  # 所有类别召回率都是1.0
        assert precisions == [1.0, 1.0, 1.0]  # 所有类别精确率都是1.0

        # 测试两次预测都错误且相同
        pred0 = [1, 0, 0, 1, 0]
        pred1 = [1, 0, 0, 1, 0]
        gt = [0, 1, 2, 0, 1]
        result = cls_evaluate_twice(pred0, pred1, gt, num_classes=3)
        assert result.accuracy == 0.0
        assert result.states == [ResultState.WRONG] * 5
        assert result.conf_mat == [[0, 2, 0], [2, 0, 0], [1, 0, 0]]
        recalls, precisions = result.recall_and_precision
        assert recalls == [0.0, 0.0, 0.0]  # 所有类别召回率都是0.0
        assert precisions == [0.0, 0.0, 0.0]  # 所有类别精确率都是0.0

    def test_unstable_predictions(self):
        """测试不稳定预测：两次预测结果不同"""
        # 测试不稳定但至少正确一次
        pred0: list[int | None] = [0, 1, 2, 0, 1]
        pred1: list[int | None] = [1, 0, 2, 1, 0]
        gt = [0, 1, 2, 0, 1]
        result = cls_evaluate_twice(pred0, pred1, gt, num_classes=3)
        assert result.accuracy == 1.0  # 所有样本都至少正确一次
        assert result.states == [
            ResultState.UNSTABLE,  # pred0正确，pred1错误
            ResultState.UNSTABLE,  # pred0正确，pred1错误
            ResultState.CORRECT,   # 两次都正确且相同
            ResultState.UNSTABLE,  # pred0正确，pred1错误
            ResultState.UNSTABLE   # pred0正确，pred1错误
        ]
        assert result.conf_mat == [[2, 0, 0], [0, 2, 0], [0, 0, 1]]

        # 测试不稳定且全部错误
        pred0 = [1, 0, 2, 1, 0]
        pred1 = [2, 1, 0, 2, 1]
        gt = [0, 1, 2, 0, 1]
        result = cls_evaluate_twice(pred0, pred1, gt, num_classes=3)
        assert result.accuracy == 0.6  # 3/5 至少正确一次
        assert result.states == [
            ResultState.UNSTABLE_WRONG,  # 都错误
            ResultState.UNSTABLE,         # pred1正确
            ResultState.UNSTABLE,         # pred0正确
            ResultState.UNSTABLE_WRONG,  # 都错误
            ResultState.UNSTABLE          # pred1正确
        ]
        assert result.conf_mat == [[0, 2, 0], [2, 0, 0], [0, 0, 1]]

    def test_none_predictions(self):
        """测试None值处理"""
        # 测试包含None值
        pred0: list[int | None] = [0, None, 2, 0, 1]
        pred1: list[int | None] = [0, 1, 2, 0, 1]
        gt = [0, 1, 2, 0, 1]
        result = cls_evaluate_twice(pred0, pred1, gt, num_classes=3)
        assert result.accuracy == 0.8  # 4/5 正确
        assert result.states == [
            ResultState.CORRECT, ResultState.NO_OUTPUT, ResultState.CORRECT,
            ResultState.CORRECT, ResultState.CORRECT
        ]
        assert result.conf_mat == [[2, 0, 0], [0, 1, 0], [0, 0, 1]]

        # 测试两次预测都有None
        pred0 = [None, None, None]
        pred1 = [None, None, None]
        gt = [0, 1, 2]
        result = cls_evaluate_twice(pred0, pred1, gt, num_classes=3)
        assert result.accuracy == 0.0
        assert result.states == [ResultState.NO_OUTPUT] * 3
        assert result.conf_mat == [[0, 0, 0], [0, 0, 0], [0, 0, 0]]

    def test_edge_cases(self):
        """测试边界情况"""
        # 单类别
        pred0: list[int | None] = [0, 0, 0]
        pred1: list[int | None] = [0, 0, 0]
        gt = [0, 0, 0]
        result = cls_evaluate_twice(pred0, pred1, gt, num_classes=1)
        assert result.accuracy == 1.0
        assert result.states == [ResultState.CORRECT] * 3
        assert result.conf_mat == [[3]]

        # 长度不匹配错误
        pred0 = [0, 1]
        pred1 = [0, 1]
        gt = [0, 1, 2]
        with pytest.raises(ValueError, match="预测结果和真实标签长度不匹配"):
            cls_evaluate_twice(pred0, pred1, gt, num_classes=3)

        # pred0和pred1长度不匹配
        pred0 = [0, 1, 2]
        pred1 = [0, 1]
        gt = [0, 1, 2]
        with pytest.raises(ValueError, match="预测结果和真实标签长度不匹配"):
            cls_evaluate_twice(pred0, pred1, gt, num_classes=3)

    def test_mixed_scenarios(self):
        """测试混合场景：包含各种状态"""
        pred0: list[int | None] = [0, 1, 2, 0, 1, None, 2]
        pred1: list[int | None] = [0, 0, 2, 1, 0, 1, None]
        gt = [0, 1, 2, 0, 1, 1, 2]
        result = cls_evaluate_twice(pred0, pred1, gt, num_classes=3)
        
        # 预期状态：
        # 样本0: pred0=0, pred1=0, gt=0 -> 两次相同且正确 -> CORRECT
        # 样本1: pred0=1, pred1=0, gt=1 -> 不同，pred0正确 -> UNSTABLE
        # 样本2: pred0=2, pred1=2, gt=2 -> 两次相同且正确 -> CORRECT
        # 样本3: pred0=0, pred1=1, gt=0 -> 不同，pred0正确 -> UNSTABLE
        # 样本4: pred0=1, pred1=0, gt=1 -> 不同，pred0正确 -> UNSTABLE
        # 样本5: pred0=None, pred1=1, gt=1 -> 有None -> NO_OUTPUT
        # 样本6: pred0=2, pred1=None, gt=2 -> 有None -> NO_OUTPUT
        
        expected_stats = [
            ResultState.CORRECT,      # 样本0
            ResultState.UNSTABLE,     # 样本1
            ResultState.CORRECT,      # 样本2
            ResultState.UNSTABLE,     # 样本3
            ResultState.UNSTABLE,     # 样本4
            ResultState.NO_OUTPUT,    # 样本5
            ResultState.NO_OUTPUT     # 样本6
        ]
        
        assert result.states == expected_stats
        assert result.accuracy == 5/7  # 5个样本至少正确一次
        assert result.conf_mat == [[2, 0, 0], [0, 2, 0], [0, 0, 1]]

    def test_return_types(self):
        """测试返回类型"""
        pred0: list[int | None] = [0, 1, 2]
        pred1: list[int | None] = [0, 1, 2]
        gt = [0, 1, 2]
        result = cls_evaluate_twice(pred0, pred1, gt, num_classes=3)
        
        # 返回类型验证
        assert isinstance(result, ClsMetric)
        assert isinstance(result.accuracy, float)
        assert isinstance(result.conf_mat, list)
        assert isinstance(result.states, list)
        assert all(isinstance(stat, ResultState) for stat in result.states)



def test_print_demo():
    """演示 ClsMetric print 函数的各种用法"""
    print("\n" + "="*50)
    print("ClsMetric Print 函数演示")
    print("="*50)
    
    # 1. 基本功能演示
    print("\n1. 基本功能演示 (默认类别名称):")
    pred: list[int | None] = [0, 1, 2, 0, 1]
    gt = [0, 1, 2, 0, 1]
    result = cls_evaluate(pred, gt, num_classes=3)
    result.print()
    
    # 2. 自定义类别名称演示
    print("\n2. 自定义类别名称演示:")
    result.print(["猫", "狗", "鸟"])
    
    # 3. 混合结果演示
    print("\n3. 混合结果演示 (包含各种状态):")
    pred_mixed: list[int | None] = [0, 1, 2, 0, 1, None]
    gt_mixed = [0, 1, 2, 1, 1, 2]
    result_mixed = cls_evaluate(pred_mixed, gt_mixed, num_classes=3)
    result_mixed.print(["猫", "狗", "鸟"])
    
    # 4. 二分类演示
    print("\n4. 二分类演示:")
    pred_binary: list[int | None] = [0, 1, 0, 1]
    gt_binary = [0, 1, 0, 1]
    result_binary = cls_evaluate(pred_binary, gt_binary, num_classes=2)
    result_binary.print(["负类", "正类"])
    
    # 5. 列宽度演示
    print("\n5. 列宽度演示 (col_width=12):")
    result.print(["短名称", "中等长度", "较长名称"], col_width=12)
    
    # 6. 错误处理演示 - 类别名称数量不匹配
    print("\n6. 错误处理演示 (类别名称数量不匹配):")
    try:
        result.print(["猫", "狗"])  # 只有2个名称，但类别数是3
    except ValueError as e:
        print(f"捕获到预期的错误: {e}")
    
    # 7. 错误处理演示 - 类别名称长度超过列宽度
    print("\n7. 错误处理演示 (类别名称长度超过列宽度):")
    try:
        result.print(["非常长的类别名称", "另一个很长的名称", "第三个超长名称"], col_width=8)
    except ValueError as e:
        print(f"捕获到预期的错误: {e}")
    
    print("\n" + "="*50)
    print("演示完成")
    print("="*50)


if __name__ == "__main__":
    pytest.main([__file__])

    test_print_demo()