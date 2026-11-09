from enum import StrEnum
from functools import cached_property

from pydantic import BaseModel, Field

__all__ = [
    "ResultState",
    "ClsMetric",
    "cls_evaluate",
    "cls_evaluate_twice",
]

class ResultState(StrEnum):
    ''' 分类结果的状态
    对于基于大模型的分类算法，结果的状态不再仅有正确和错误两种，而是有多种可能性。按照以下规则分类。
    前三种状态可以同时用于单次和多次评估。后两种状态只能用于多次评估。
    '''

    CORRECT = "正确"
    '''结果正确。如果预测多次，结果相同。'''

    WRONG = "错误"
    '''结果错误。如果预测多次，结果相同。'''

    NO_OUTPUT = "未输出"
    '''未正确计算出结果，例如发生异常。如果预测多次，至少有一次未输出。'''
    
    UNSTABLE = "不稳定"
    '''预测多次，结果不同，但至少正确一次。'''

    UNSTABLE_WRONG = "不稳定错误"
    '''预测多次，结果不同，且全部错误。这是最糟糕的情况。'''


class ClsMetric(BaseModel):
    """分类指标统计"""
    accuracy: float = Field(..., description="准确率")
    '''即分类正确的样本数量占总样本数量的比例。accuracy = 正确数量 / 总样本数'''

    conf_mat: list[list[int]] = Field(..., description="混淆矩阵")
    '''conf_mat[i][j] 表示真实标签为 i，预测为 j 的样本数量。
    行索引 i 为真实类别，列索引 j 为预测类别。
    例如，对于二分类，如果真实为1预测为0，则 conf_mat[1][0] += 1。
    '''

    @cached_property
    def recall_and_precision(self) -> tuple[list[float], list[float]]:
        '''计算每个类别的召回率和精确率
        recall = 正确识别为该类别的数量 / 该类别的真实样本数量
        precision = 正确识别为该类别的数量 / 该类别的预测样本数量
        '''
        recalls = []
        precisions = []

        num_classes = len(self.conf_mat)
        
        for i in range(num_classes):
            # 计算召回率：TP / (TP + FN)
            # TP = conf_mat[i][i], FN = sum(conf_mat[i][j] for j != i)
            tp = self.conf_mat[i][i]
            fn = sum(self.conf_mat[i][j] for j in range(num_classes) if j != i)
            recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
            recalls.append(recall)
            
            # 计算精确率：TP / (TP + FP)
            # TP = conf_mat[i][i], FP = sum(conf_mat[j][i] for j != i)
            fp = sum(self.conf_mat[j][i] for j in range(num_classes) if j != i)
            precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
            precisions.append(precision)
        return recalls, precisions

    states: list[ResultState] = Field(..., description="每个样本的状态")


    @cached_property
    def state_indices(self) -> dict[ResultState, list[int]]:
        '''计算属于各个状态的样本索引'''
        state_indices: dict[ResultState, list[int]] = {state: [] for state in ResultState}
        for i, state in enumerate(self.states):
            state_indices[state].append(i)
        return state_indices


    def print(self, class_names: list[str] | None = None, col_width: int = 8):
        '''
        打印分类指标统计结果。
        TODO: 不是直接print，而是返回list[str]，然后调用者再打印。

        class_names: 类别名称列表，用于打印混淆矩阵, recalls和precisions。如果为None, 则使用数字索引。
        col_width: 列宽度，用于格式化输出。所有列将使用此宽度。
        '''
        num_classes = len(self.conf_mat)
        
        # 确定类别名称
        if class_names is None:
            class_names = [str(i) for i in range(num_classes)]
        elif len(class_names) != num_classes:
            raise ValueError(f"类别名称数量({len(class_names)})与类别数({num_classes})不匹配")
        
        # 检查类别名称长度是否超过列宽度
        for i, name in enumerate(class_names):
            if len(name) > col_width:
                raise ValueError(f"类别名称 '{name}' (索引{i}) 长度({len(name)})超过列宽度({col_width})")
        
        print("=== 分类指标统计 ===")
        print(f"准确率: {self.accuracy:.4f}")
        print()
        
        # 打印召回率和精确率
        print("各类别指标:")
        print(f"{'类别':<{col_width}} {'召回率':<10} {'精确率':<10}")
        print("-" * (col_width + 20))

        recalls, precisions = self.recall_and_precision

        for i in range(num_classes):
            print(f"{class_names[i]:<{col_width}} {recalls[i]:<10.4f} {precisions[i]:<10.4f}")
        print()
        
        # 打印混淆矩阵
        print("混淆矩阵:")
        print(f"{'真实\\预测':<{col_width}}", end="")
        for j in range(num_classes):
            print(f"{class_names[j]:<{col_width}}", end="")
        print()
        print("-" * (col_width + col_width * num_classes))
        
        for i in range(num_classes):
            print(f"{class_names[i]:<{col_width}}", end="")
            for j in range(num_classes):
                print(f"{self.conf_mat[i][j]:<{col_width}}", end="")
            print()
        print()
        
        # 打印样本状态统计
        print("样本状态统计:")
        for state in ResultState:
            count = len(self.state_indices[state])
            percentage = count / len(self.states) * 100 if len(self.states) > 0 else 0
            print(f"  {state}: {count} ({percentage:.1f}%)")


def cls_evaluate(pred: list[int | None], gt: list[int], *, num_classes: int) -> ClsMetric:
    """计算分类指标。

    pred: list[int | None]: 预测结果。None表示未输出预测结果。
    gt: list[int]: 真实标签。
    num_classes: int: 类别数。gt和pred中的值属于[0, num_classes-1]。
    
    根据ResultState的定义计算每个样本的状态, 并返回准确率、混淆矩阵。
    """
    if len(pred) != len(gt):
        raise ValueError("预测结果和真实标签长度不匹配")
    
    stats = []
    correct_count = 0
    total_samples = len(pred)
    
    # 初始化混淆矩阵 (num_classes x num_classes)
    conf_mat = [[0 for _ in range(num_classes)] for _ in range(num_classes)]
    
    for i in range(total_samples):
        pred_val = pred[i]
        gt_val = gt[i]
        
        if pred_val is None:
            # 未输出预测结果
            stats.append(ResultState.NO_OUTPUT)
        elif pred_val == gt_val:
            # 预测正确
            stats.append(ResultState.CORRECT)
            correct_count += 1
            conf_mat[gt_val][pred_val] += 1
        else:
            # 预测错误
            stats.append(ResultState.WRONG)
            conf_mat[gt_val][pred_val] += 1
    
    # 计算准确率
    accuracy = correct_count / total_samples if total_samples > 0 else 0.0
    
    return ClsMetric(
        accuracy=accuracy,
        conf_mat=conf_mat,
        states=stats
    )


def cls_evaluate_twice(pred0: list[int | None], pred1: list[int | None], gt: list[int], *, num_classes: int) -> ClsMetric:
    """计算两次分类结果的指标，用于分析分类算法输出结果不稳定的情况。

    pred0,1: list[int | None]: 两次预测结果。None表示未输出预测结果。
    gt: list[int]: 真实标签。
    num_classes: int: 类别数。gt和pred中的值属于[0, num_classes-1]。
    
    根据ResultState的定义计算每个样本的状态, 并返回准确率、混淆矩阵。
    """
    if len(pred0) != len(pred1) or len(pred0) != len(gt):
        raise ValueError("预测结果和真实标签长度不匹配")
    
    stats = []
    correct_count = 0
    total_samples = len(pred0)
    
    # 初始化混淆矩阵 (num_classes x num_classes)
    conf_mat = [[0 for _ in range(num_classes)] for _ in range(num_classes)]
    
    for i in range(total_samples):
        pred0_val = pred0[i]
        pred1_val = pred1[i]
        gt_val = gt[i]
        
        # 判断状态
        if pred0_val is None or pred1_val is None:
            # 至少有一次未输出
            stats.append(ResultState.NO_OUTPUT)
        elif pred0_val == pred1_val:
            # 两次预测结果相同
            if pred0_val == gt_val:
                # 预测正确
                stats.append(ResultState.CORRECT)
                correct_count += 1
                conf_mat[gt_val][pred0_val] += 1
            else:
                # 预测错误
                stats.append(ResultState.WRONG)
                conf_mat[gt_val][pred0_val] += 1
        else:
            # 两次预测结果不同
            pred0_correct = pred0_val == gt_val
            pred1_correct = pred1_val == gt_val
            
            if pred0_correct or pred1_correct:
                # 至少正确一次
                stats.append(ResultState.UNSTABLE)
                correct_count += 1
                # 使用第一次预测结果更新混淆矩阵
                conf_mat[gt_val][pred0_val] += 1
            else:
                # 全部错误
                stats.append(ResultState.UNSTABLE_WRONG)
                # 使用第一次预测结果更新混淆矩阵
                conf_mat[gt_val][pred0_val] += 1
    
    accuracy = correct_count / total_samples
    
    return ClsMetric(
        accuracy=accuracy,
        conf_mat=conf_mat,
        states=stats
    )



# TODO: 对比两组ClsMetric

class ClsMetricDiff(BaseModel):
    pass


def compare_cls_metrics(metric0: ClsMetric, metric1: ClsMetric) -> ClsMetricDiff:
    pass


class ClsCompareResult(BaseModel):
    improved: list[int] = Field(default_factory=list, description="预测更正确的样本索引")
    degraded: list[int] = Field(default_factory=list, description="预测更错误的样本索引")
    same_correct: list[int] = Field(default_factory=list, description="预测不变的正确样本索引")
    same_wrong: list[int] = Field(default_factory=list, description="预测不变的错误样本索引")

    ## model_not_output: list[int] = Field(default_factory=list, description="模型未输出样本索引")


class DisagreementAnalysisResult(BaseModel):
    """模型分歧分析结果"""
    total_disagreements: int = Field(..., description="总分歧数")
    disagreement_indices: list[int] = Field(default_factory=list, description="分歧样本索引")
    pred0_correct_in_disagreements: int = Field(..., description="分歧样本中pred0正确的数量")
    pred1_correct_in_disagreements: int = Field(..., description="分歧样本中pred1正确的数量")
    both_wrong_in_disagreements: int = Field(..., description="分歧样本中都错的数量")
    both_correct_in_disagreements: int = Field(default=0, description="分歧样本中都对的数量（理论上为0）")
    pred0_correct_ratio: float = Field(..., description="pred0在分歧样本中的正确率")
    pred1_correct_ratio: float = Field(..., description="pred1在分歧样本中的正确率")
    both_wrong_ratio: float = Field(..., description="都错的比例")
    
    def print(self, prefix: str = ""):
        """打印分歧分析结果"""
        print(f"{prefix}=== 模型分歧分析 (Disagreement Analysis) ===")
        print(f"{prefix}总分歧数: {self.total_disagreements}")
        print(f"{prefix}分歧样本中:")
        print(f"{prefix}  - pred1 正确的比例: {self.pred1_correct_in_disagreements}/{self.total_disagreements} ({self.pred1_correct_ratio:.2%})")
        print(f"{prefix}  - pred0 正确的比例: {self.pred0_correct_in_disagreements}/{self.total_disagreements} ({self.pred0_correct_ratio:.2%})")
        print(f"{prefix}  - 都错的比例: {self.both_wrong_in_disagreements}/{self.total_disagreements} ({self.both_wrong_ratio:.2%})")
        if self.pred1_correct_ratio > self.pred0_correct_ratio:
            print(f"{prefix}✓ 结论: pred1 在分歧样本中胜率更高，则说明它更有\"独立判断能力\"")
        elif self.pred0_correct_ratio > self.pred1_correct_ratio:
            print(f"{prefix}✓ 结论: pred0 在分歧样本中胜率更高，则说明它更有\"独立判断能力\"")
        else:
            print(f"{prefix}✓ 结论: pred0 和 pred1 在分歧样本中表现相当")


def cls_compare(pred0: list[int], pred1: list[int], gt: list[int]) -> ClsCompareResult:
    result = ClsCompareResult()
    for i in range(len(gt)):
        pred0_correct = pred0[i] == gt[i]
        pred1_correct = pred1[i] == gt[i]
        
        if pred0_correct and pred1_correct:
            result.same_correct.append(i)      # 两个都对
        elif not pred0_correct and not pred1_correct:
            result.same_wrong.append(i)         # 两个都错
        elif not pred0_correct and pred1_correct:
            result.improved.append(i)           # pred1改进了
        elif pred0_correct and not pred1_correct:
            result.degraded.append(i)           # pred1退化了
    
    return result


def check_cls_compare_samples(pred0: list[int], pred1: list[int], gt: list[int], samples: list[str]) -> ClsCompareResult:
    cmp_result = cls_compare(pred0, pred1, gt)
    for i in cmp_result.improved:
        print(f"样本{i}预测更正确: {samples[i]}")
    for i in cmp_result.degraded:
        print(f"样本{i}预测更错误: {samples[i]}")
    for i in cmp_result.same_correct:
        print(f"样本{i}预测不变的正确: {samples[i]}")
    for i in cmp_result.same_wrong:
        print(f"样本{i}预测不变的错误: {samples[i]}")

    return cmp_result



def disagreement_analysis(pred0: list[int], pred1: list[int], gt: list[int]) -> DisagreementAnalysisResult:
    """模型分歧分析
    
    分析两个模型预测结果的分歧情况，用于判断哪个模型更有"独立判断能力"。
    
    :param pred0: 第一个模型的预测标签
    :param pred1: 第二个模型的预测标签
    :param gt: 真实标签
    :return: 分歧分析结果对象
    
    使用示例:
        pred0 = [0, 1, 1, 0, 1, 0, 1]
        pred1 = [0, 1, 0, 1, 1, 0, 0]
        gt    = [0, 1, 0, 0, 1, 0, 1]
        
        result = disagreement_analysis(pred0, pred1, gt)
        result.print()
    """
    disagreement_indices = []
    pred0_correct_count = 0
    pred1_correct_count = 0
    both_wrong_count = 0
    both_correct_count = 0
    
    # 找出所有分歧样本
    for i in range(len(pred0)):
        if pred0[i] != pred1[i]:  # 预测不一致
            disagreement_indices.append(i)
            
            pred0_correct = pred0[i] == gt[i]
            pred1_correct = pred1[i] == gt[i]
            
            if pred0_correct and pred1_correct:
                both_correct_count += 1  # 理论上不会出现（因为预测不一致）
            elif pred0_correct and not pred1_correct:
                pred0_correct_count += 1
            elif not pred0_correct and pred1_correct:
                pred1_correct_count += 1
            else:  # 都错
                both_wrong_count += 1
    
    total_disagreements = len(disagreement_indices)
    
    # 避免除以0
    if total_disagreements == 0:
        pred0_correct_ratio = 0.0
        pred1_correct_ratio = 0.0
        both_wrong_ratio = 0.0
    else:
        pred0_correct_ratio = pred0_correct_count / total_disagreements
        pred1_correct_ratio = pred1_correct_count / total_disagreements
        both_wrong_ratio = both_wrong_count / total_disagreements
    
    return DisagreementAnalysisResult(
        total_disagreements=total_disagreements,
        disagreement_indices=disagreement_indices,
        pred0_correct_in_disagreements=pred0_correct_count,
        pred1_correct_in_disagreements=pred1_correct_count,
        both_wrong_in_disagreements=both_wrong_count,
        both_correct_in_disagreements=both_correct_count,
        pred0_correct_ratio=pred0_correct_ratio,
        pred1_correct_ratio=pred1_correct_ratio,
        both_wrong_ratio=both_wrong_ratio
    )
