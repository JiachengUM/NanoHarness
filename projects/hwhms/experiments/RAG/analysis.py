import pandas as pd
import numpy as np
from pathlib import Path
import sys

# 添加项目根目录到 Python 路径
project_root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from projects.hwhms.common.cls_analyze import cls_evaluate
import matplotlib.pyplot as plt

def _compute_pr_with_cls_evaluate(y_true: np.ndarray, y_scores: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """使用 ClsEvaluate 直接计算 PR 曲线点（正类）。"""
    unique_scores = np.unique(y_scores.astype(float))
    if unique_scores.size == 0:
        return np.array([]), np.array([])
    thresholds = unique_scores[::-1]

    precisions: list[float] = []
    recalls: list[float] = []
    for thr in thresholds:
        y_pred = (y_scores >= thr).astype(int)
        metric = cls_evaluate(pred=y_pred.tolist(), gt=y_true.astype(int).tolist(), num_classes=2)
        r_list, p_list = metric.recall_and_precision
        recalls.append(r_list[1] if len(r_list) > 1 else 0.0)
        precisions.append(p_list[1] if len(p_list) > 1 else 0.0)

    return np.array(recalls, dtype=float), np.array(precisions, dtype=float)


def load_data():
    """加载正负样本数据"""
    here = Path(__file__).resolve().parent
    
    # 读取正样本数据
    positive_df = pd.read_csv(here / "positive_results.csv")
    positive_df['label'] = 1  # 正样本标签
    
    # 读取负样本数据
    negative_df = pd.read_csv(here / "negative_results.csv")
    negative_df['label'] = 0  # 负样本标签
    
    # 合并数据
    all_data = pd.concat([positive_df, negative_df], ignore_index=True)
    
    return all_data


def plot_score_distribution(y_true: np.ndarray, y_scores: np.ndarray, save_path: str = 'score_distribution.png'):
    """绘制正负样本分布图"""
    positives = y_scores[y_true == 1]
    negatives = y_scores[y_true == 0]

    plt.figure(figsize=(8, 5))
    plt.hist(positives, bins=50, alpha=0.6, label='Positive', color='#2ca02c')
    plt.hist(negatives, bins=50, alpha=0.6, label='Negative', color='#1f77b4')
    plt.xlabel('Similarity score')
    plt.ylabel('Count')
    plt.title('Score Distribution (Positive vs Negative)')
    plt.legend()
    plt.tight_layout()
    plt.savefig(save_path, dpi=200)
    plt.close()


def plot_precision_recall_curve(y_true: np.ndarray, y_scores: np.ndarray, save_path: str = 'precision_recall_curve.png'):
    """绘制0.8-1.0段的Precision-Recall曲线（基于 ClsMetric）"""
    recall, precision = _compute_pr_with_cls_evaluate(y_true, y_scores)

    plt.figure(figsize=(7, 6))
    plt.plot(recall, precision, color='#d62728', lw=2.0, label='PR curve')
    plt.xlabel('Recall')
    plt.ylabel('Precision')
    plt.title('Precision-Recall Curve (Zoomed 0.80–1.00)')
    
    # 仅展示 0.8–1.0 段
    plt.xlim(0.80, 1.00)
    plt.ylim(0.80, 1.00)
    
    # 清晰刻度
    ticks = np.linspace(0.80, 1.00, 11)
    tick_labels = [f"{t:.2f}" for t in ticks]
    plt.xticks(ticks, tick_labels)
    plt.yticks(ticks, tick_labels)
    
    # 网格
    plt.grid(True, linestyle='--', alpha=0.5, which='both')
    plt.legend(loc='lower left')
    plt.tight_layout()
    plt.savefig(save_path, dpi=300)
    plt.close()
    
    return recall, precision


def find_best_threshold(y_true: np.ndarray, y_scores: np.ndarray) -> dict:
    """找到F1最大的阈值"""
    # 获取所有唯一的分数作为候选阈值
    unique_scores = np.unique(y_scores)
    unique_scores = np.sort(unique_scores)[::-1]  # 从高到低排序
    
    best_f1 = 0
    best_threshold = 0
    best_precision = 0
    best_recall = 0
    
    results = []
    
    for threshold in unique_scores:
        # 根据阈值预测
        y_pred = (y_scores >= threshold).astype(int)
        
        # 计算指标
        metric = cls_evaluate(pred=y_pred.tolist(), gt=y_true.astype(int).tolist(), num_classes=2)
        r_list, p_list = metric.recall_and_precision
        
        # 获取正类的precision和recall
        precision = p_list[1] if len(p_list) > 1 else 0.0
        recall = r_list[1] if len(r_list) > 1 else 0.0
        
        # 计算F1
        if precision + recall > 0:
            f1 = 2 * precision * recall / (precision + recall)
        else:
            f1 = 0
        
        results.append({
            'threshold': threshold,
            'precision': precision,
            'recall': recall,
            'f1': f1
        })
        
        # 更新最佳结果
        if f1 > best_f1:
            best_f1 = f1
            best_threshold = threshold
            best_precision = precision
            best_recall = recall
    
    return {
        'best_threshold': best_threshold,
        'best_f1': best_f1,
        'best_precision': best_precision,
        'best_recall': best_recall,
        'all_results': results
    }


def print_threshold_analysis(results: dict):
    """打印阈值分析结果"""
    print("=" * 60)
    print("阈值优化分析结果")
    print("=" * 60)
    print(f"最佳阈值: {results['best_threshold']:.6f}")
    print(f"最佳F1分数: {results['best_f1']:.6f}")
    print(f"对应Precision: {results['best_precision']:.6f}")
    print(f"对应Recall: {results['best_recall']:.6f}")
    # 按F1排序
    sorted_results = sorted(results['all_results'], key=lambda x: x['f1'], reverse=True)
    for i, result in enumerate(sorted_results[:10]):
        print(f"{result['threshold']:<12.6f} {result['precision']:<12.6f} {result['recall']:<12.6f} {result['f1']:<12.6f}")


def main():
    """主函数"""
    # 加载数据
    all_data = load_data()
    here = Path(__file__).resolve().parent
    
    # 准备数据
    y_true = all_data['label'].values
    y_scores = all_data['max_similarity'].values
    
    # 找到最佳阈值
    threshold_results = find_best_threshold(y_true, y_scores)
    print_threshold_analysis(threshold_results)
    
    # 绘制正负样本分布图
    plot_score_distribution(y_true, y_scores, save_path=str(here / 'score_distribution.png'))
    
    # 绘制 Precision-Recall 曲线
    plot_precision_recall_curve(y_true, y_scores, save_path=str(here / 'precision_recall_curve.png'))
    
    print("\n分析完成！图表已保存为:")
    print("- score_distribution.png (正负样本分布图)")
    print("- precision_recall_curve.png (Precision-Recall曲线)")


if __name__ == "__main__":
    main()
