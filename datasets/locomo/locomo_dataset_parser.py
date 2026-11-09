#!/usr/bin/env python3
"""
LOCOMO Dataset Parser
用于解析和分析LOCOMO长期记忆对话数据集
"""

import json
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Any, Union
from pydantic import BaseModel, field_validator
from collections import Counter, defaultdict
import matplotlib.pyplot as plt


class DialogueTurn(BaseModel):
    """对话轮次数据结构"""
    speaker: str
    dia_id: str
    text: str
    session_id: int
    turn_id: int


class QAItem(BaseModel):
    """问答对数据结构"""
    question: str
    answer: Union[str, int, None] = None
    evidence: List[str]
    category: int


class Session(BaseModel):
    """会话数据结构"""
    date_time: str
    dia: List[Dict[str, Any]]

    def __chat_str__(self) -> str:
        return '\n'.join([f"{d['speaker']}: {d['text']}" for d in self.dia])


class Conversation(BaseModel):
    """对话数据结构"""
    speaker_a: str
    speaker_b: str
    sessions: List[Session]

    model_config = {
        "extra": "forbid",
    }


class Event(BaseModel):
    """事件数据结构"""
    a_event: List[str]
    b_event: List[str]
    date: str


class LOCOMOSample(BaseModel):
    """LOCOMO样本数据结构"""
    qa: List[QAItem]
    conversation: Conversation
    event_summary: List[Event]
    observation: Any
    session_summary: Dict[str, str]

    @field_validator('event_summary', mode='before')
    @classmethod
    def convert_event_summary(cls, v: Dict[str, Dict] | List[Event]) -> List[Event]:
        if isinstance(v, list):
            return v
        
        assert isinstance(v, dict)
        
        events = []
        n = 1
        while True:
            event_key = f'events_session_{n}'
            if event_key not in v:
                break

            event_data = v[event_key]
            assert isinstance(event_data, dict)
            event = Event(a_event=[], b_event=[], date=event_data['date'])
            events.append(event)
            n += 1

        return events
    
    @field_validator('conversation', mode='before')
    @classmethod
    def convert_conversation(cls, v: Dict | Conversation) -> Conversation:
        """将conversation字段从dict转换为Conversation对象"""
        if isinstance(v, Conversation):
            return v
        
        assert isinstance(v, dict)
        
        # 提取speaker_a和speaker_b
        speaker_a = v['speaker_a']
        speaker_b = v['speaker_b']
        
        # 收集所有session
        sessions = []
        
        # 从1开始依次增大序号，直到找不到对应的session字段
        n = 1
        while True:
            session_key = f'session_{n}'
            date_time_key = f'session_{n}_date_time'
            
            # 如果session_n字段不存在，则停止
            if session_key not in v:
                break
            
            # 转换dialogues
            dialogues = []
            for dialogue_data in v[session_key]:
                assert isinstance(dialogue_data, dict)
                dialogues.append(dialogue_data)
            
            # 创建session
            session = Session(
                date_time=v[date_time_key],
                dia=dialogues
            )
            sessions.append(session)
            
            n += 1
        
        return Conversation(
            speaker_a=speaker_a,
            speaker_b=speaker_b,
            sessions=sessions
        )


class LOCOMODataset:
    """LOCOMO数据集解析器"""
    
    def __init__(self, file_path: str):
        """
        初始化数据集解析器
        
        Args:
            file_path: LOCOMO数据集JSON文件路径
        """
        self.file_path = file_path
        self.data = None
        self.samples = []
        self.load_data()
    
    def load_data(self):
        """加载数据集"""
        print(f"正在加载LOCOMO数据集: {self.file_path}")
        with open(self.file_path, 'r', encoding='utf-8') as f:
            self.data = json.load(f)
        
        # 解析所有样本
        for i, sample_data in enumerate(self.data):
            try:
                sample = LOCOMOSample(**sample_data)
                self.samples.append(sample)
            except Exception as e:
                print(f"解析样本 {i} 时出错: {e}")
                continue
        
        print(f"成功加载 {len(self.samples)} 个样本")
    
    def get_dialogue_turns(self, sample_id: int = 0) -> List[DialogueTurn]:
        """获取指定样本的所有对话轮次"""
        sample = self.samples[sample_id]
        turns = []
        
        for session_id, session in enumerate(sample.conversation.sessions, 1):
            for turn_id, turn_data in enumerate(session.dia):
                turn = DialogueTurn(
                    speaker=turn_data['speaker'],
                    dia_id=turn_data['dia_id'],
                    text=turn_data['text'],
                    session_id=session_id,
                    turn_id=turn_id
                )
                turns.append(turn)
        
        return sorted(turns, key=lambda x: (x.session_id, x.turn_id))
    
    def get_qa_by_category(self, sample_id: int = 0) -> Dict[int, List[QAItem]]:
        """按类别获取问答对"""
        sample = self.samples[sample_id]
        qa_by_category = defaultdict(list)
        
        for qa_item in sample.qa:
            qa_by_category[qa_item.category].append(qa_item)
        
        return dict(qa_by_category)
    
    def analyze_dataset(self) -> Dict[str, Any]:
        """分析数据集统计信息"""
        stats = {
            'total_samples': len(self.samples),
            'total_qa_pairs': sum(len(sample.qa) for sample in self.samples),
            'qa_categories': Counter(),
            'speakers': set(),
            'total_sessions': 0,
            'total_dialogue_turns': 0
        }
        
        for sample in self.samples:
            # 统计问答类别
            for qa_item in sample.qa:
                stats['qa_categories'][qa_item.category] += 1
            
            # 统计对话信息
            turns = self.get_dialogue_turns(self.samples.index(sample))
            stats['total_dialogue_turns'] += len(turns)
            
            # 统计说话者
            for turn in turns:
                stats['speakers'].add(turn.speaker)
            
            # 统计会话数
            session_ids = set(turn.session_id for turn in turns)
            stats['total_sessions'] += len(session_ids)
        
        stats['speakers'] = list(stats['speakers'])
        return stats
    
    def get_sample_summary(self, sample_id: int = 0) -> Dict[str, Any]:
        """获取单个样本的摘要信息"""
        sample = self.samples[sample_id]
        turns = self.get_dialogue_turns(sample_id)
        qa_by_category = self.get_qa_by_category(sample_id)
        
        return {
            'sample_id': sample_id,
            'total_dialogue_turns': len(turns),
            'total_sessions': len(set(turn.session_id for turn in turns)),
            'speakers': list(set(turn.speaker for turn in turns)),
            'total_qa_pairs': len(sample.qa),
            'qa_by_category': {cat: len(qa_list) for cat, qa_list in qa_by_category.items()},
            'session_range': (
                min(turn.session_id for turn in turns),
                max(turn.session_id for turn in turns)
            ) if turns else (0, 0)
        }
    
    def search_qa_by_keyword(self, keyword: str, sample_id: int = None) -> List[Tuple[int, QAItem]]:
        """根据关键词搜索问答对"""
        results = []
        
        samples_to_search = [sample_id] if sample_id is not None else range(len(self.samples))
        
        for sid in samples_to_search:
            sample = self.samples[sid]
            for qa_item in sample.qa:
                if (keyword.lower() in qa_item.question.lower() or 
                    keyword.lower() in str(qa_item.answer).lower()):
                    results.append((sid, qa_item))
        
        return results
    
    def analyze_car_suitability(self) -> Dict[str, Any]:
        """简单分析哪些对话适合车端大模型测试"""
        car_keywords = ['car', 'drive', 'road', 'travel', 'trip', 'music', 'food', 'work', 'family', 'kids', 'school', 'meeting', 'schedule']
        medical_keywords = ['medical', 'doctor', 'hospital', 'surgery', 'treatment', 'diagnosis']
        complex_keywords = ['study', 'learn', 'education', 'art', 'painting', 'technique']
        
        results = {}
        
        for sample_id in range(len(self.samples)):
            sample = self.samples[sample_id]
            turns = self.get_dialogue_turns(sample_id)
            
            # 统计关键词出现次数
            car_count = 0
            medical_count = 0
            complex_count = 0
            
            for turn in turns:
                text_lower = turn.text.lower()
                for keyword in car_keywords:
                    if keyword in text_lower:
                        car_count += 1
                        break
                
                for keyword in medical_keywords:
                    if keyword in text_lower:
                        medical_count += 1
                        break
                
                for keyword in complex_keywords:
                    if keyword in text_lower:
                        complex_count += 1
                        break
            
            # 计算适用性评分
            total_turns = len(turns)
            car_ratio = car_count / total_turns if total_turns > 0 else 0
            medical_ratio = medical_count / total_turns if total_turns > 0 else 0
            complex_ratio = complex_count / total_turns if total_turns > 0 else 0
            
            # 简单评分规则：车载相关多，医疗/复杂内容少
            suitability_score = car_ratio * 10 - medical_ratio * 5 - complex_ratio * 3
            
            results[f'sample_{sample_id}'] = {
                'total_turns': total_turns,
                'car_related': car_count,
                'medical_content': medical_count,
                'complex_content': complex_count,
                'car_ratio': car_ratio,
                'medical_ratio': medical_ratio,
                'complex_ratio': complex_ratio,
                'suitability_score': suitability_score,
                'recommendation': '推荐' if suitability_score > 0.5 else '不推荐' if suitability_score < 0 else '一般'
            }
        
        return results
    
    def export_to_csv(self, output_dir: str = "locomo_analysis"):
        """导出分析结果到CSV文件"""
        import os
        os.makedirs(output_dir, exist_ok=True)
        
        # 导出对话数据
        for sample_id in range(len(self.samples)):
            turns = self.get_dialogue_turns(sample_id)
            df_turns = pd.DataFrame([
                {
                    'sample_id': sample_id,
                    'session_id': turn.session_id,
                    'turn_id': turn.turn_id,
                    'speaker': turn.speaker,
                    'dia_id': turn.dia_id,
                    'text': turn.text
                }
                for turn in turns
            ])
            df_turns.to_csv(f"{output_dir}/sample_{sample_id}_dialogue.csv", index=False)
        
        # 导出问答数据
        for sample_id in range(len(self.samples)):
            sample = self.samples[sample_id]
            df_qa = pd.DataFrame([
                {
                    'sample_id': sample_id,
                    'question': qa.question,
                    'answer': qa.answer,
                    'evidence': ';'.join(qa.evidence),
                    'category': qa.category
                }
                for qa in sample.qa
            ])
            df_qa.to_csv(f"{output_dir}/sample_{sample_id}_qa.csv", index=False)
        
        print(f"数据已导出到 {output_dir} 目录")
    
    def visualize_statistics(self):
        """可视化数据集统计信息"""
        stats = self.analyze_dataset()
        
        # 设置中文字体
        plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'SimHei', 'DejaVu Sans']
        plt.rcParams['axes.unicode_minus'] = False
        
        # 创建图表
        fig, axes = plt.subplots(2, 2, figsize=(16, 12))
        
        # 1. 问答类别分布
        categories = list(stats['qa_categories'].keys())
        counts = list(stats['qa_categories'].values())
        bars1 = axes[0, 0].bar(categories, counts, color='skyblue', alpha=0.8)
        axes[0, 0].set_title('问答类别分布 (QA Categories Distribution)', fontsize=14, fontweight='bold')
        axes[0, 0].set_xlabel('类别 (Category)', fontsize=12)
        axes[0, 0].set_ylabel('数量 (Count)', fontsize=12)
        
        # 添加数值标签
        for bar, count in zip(bars1, counts):
            height = bar.get_height()
            axes[0, 0].text(bar.get_x() + bar.get_width()/2., height + 10,
                           f'{count}\n({count/sum(counts)*100:.1f}%)',
                           ha='center', va='bottom', fontsize=10, fontweight='bold')
        
        # 2. 样本对话轮次分布
        sample_turn_counts = [len(self.get_dialogue_turns(i)) for i in range(len(self.samples))]
        bars2 = axes[0, 1].bar(range(len(self.samples)), sample_turn_counts, color='lightgreen', alpha=0.8)
        axes[0, 1].set_title('各样本对话轮次分布 (Dialogue Turns per Sample)', fontsize=14, fontweight='bold')
        axes[0, 1].set_xlabel('样本ID (Sample ID)', fontsize=12)
        axes[0, 1].set_ylabel('对话轮次数量 (Number of Turns)', fontsize=12)
        
        # 添加数值标签
        for bar, count in zip(bars2, sample_turn_counts):
            height = bar.get_height()
            axes[0, 1].text(bar.get_x() + bar.get_width()/2., height + 20,
                           f'{count}',
                           ha='center', va='bottom', fontsize=10, fontweight='bold')
        
        # 3. 样本问答对分布
        sample_qa_counts = [len(sample.qa) for sample in self.samples]
        bars3 = axes[1, 0].bar(range(len(self.samples)), sample_qa_counts, color='lightcoral', alpha=0.8)
        axes[1, 0].set_title('各样本问答对分布 (QA Pairs per Sample)', fontsize=14, fontweight='bold')
        axes[1, 0].set_xlabel('样本ID (Sample ID)', fontsize=12)
        axes[1, 0].set_ylabel('问答对数量 (Number of QA Pairs)', fontsize=12)
        
        # 添加数值标签
        for bar, count in zip(bars3, sample_qa_counts):
            height = bar.get_height()
            axes[1, 0].text(bar.get_x() + bar.get_width()/2., height + 5,
                           f'{count}',
                           ha='center', va='bottom', fontsize=10, fontweight='bold')
        
        # 4. 各样本车载适用性评分
        car_analysis = self.analyze_car_suitability()
        sample_names = list(car_analysis.keys())
        suitability_scores = [car_analysis[name]['suitability_score'] for name in sample_names]
        
        # 创建颜色映射：高分绿色，低分红色
        colors = ['green' if score > 2 else 'orange' if score > 1 else 'red' for score in suitability_scores]
        
        bars4 = axes[1, 1].bar(range(len(sample_names)), suitability_scores, color=colors, alpha=0.8)
        axes[1, 1].set_title('各样本车载适用性评分 (Car Suitability Score per Sample)', fontsize=14, fontweight='bold')
        axes[1, 1].set_xlabel('样本ID (Sample ID)', fontsize=12)
        axes[1, 1].set_ylabel('适用性评分 (Suitability Score)', fontsize=12)
        axes[1, 1].set_xticks(range(len(sample_names)))
        axes[1, 1].set_xticklabels([name.replace('sample_', '') for name in sample_names])
        
        # 添加数值标签
        for bar, score in zip(bars4, suitability_scores):
            height = bar.get_height()
            axes[1, 1].text(bar.get_x() + bar.get_width()/2., height + 0.1,
                           f'{score:.2f}',
                           ha='center', va='bottom', fontsize=10, fontweight='bold')
        

        
        # 添加总统计信息
        fig.suptitle(f'LOCOMO数据集统计信息\n'
                    f'总样本: {stats["total_samples"]} | '
                    f'总问答对: {stats["total_qa_pairs"]} | '
                    f'总对话轮次: {stats["total_dialogue_turns"]} | '
                    f'说话者数量: {len(stats["speakers"])}',
                    fontsize=16, fontweight='bold', y=0.98)
        
        plt.tight_layout()
        plt.subplots_adjust(top=0.92)
        plt.savefig('locomo_statistics.png', dpi=300, bbox_inches='tight')
        plt.show()


def convert_locomo_format(file_path: str, output_path: str):
    """转换LOCOMO格式，类似locomo10.py的功能"""
    with open(file_path, "r", encoding='utf-8') as f:
        data = json.load(f)

    for idx, item in enumerate(data):
        try:
            # 使用LOCOMOSample模型解析数据
            conv_all = LOCOMOSample(**item)     
        except Exception as e:
            print(f"Error processing item {idx}: {e}")
            continue

        output_file = f"{output_path}/conv_{idx}.json"
        with open(output_file, "w", encoding='utf-8') as f:
            json.dump(conv_all.model_dump(), f, indent=4, ensure_ascii=False)


def main():
    """主函数 - 演示如何使用LOCOMO数据集解析器"""
    
    # 使用绝对路径
    import os
    current_dir = os.path.dirname(os.path.abspath(__file__))
    data_file = os.path.join(current_dir, 'locomo10.json')
    
    print(f"数据文件路径: {data_file}")
    
    # 初始化数据集
    dataset = LOCOMODataset(data_file)
    
    # 1. 显示数据集统计信息
    print("=== LOCOMO 数据集统计信息 ===")
    stats = dataset.analyze_dataset()
    print(f"总样本数: {stats['total_samples']}")
    print(f"总问答对数: {stats['total_qa_pairs']}")
    print(f"总会话数: {stats['total_sessions']}")
    print(f"总对话轮次: {stats['total_dialogue_turns']}")
    print(f"说话者: {stats['speakers']}")
    print(f"问答类别分布: {dict(stats['qa_categories'])}")
    
    # 2. 显示第一个样本的摘要
    print("\n=== 样本 0 摘要 ===")
    summary = dataset.get_sample_summary(0)
    for key, value in summary.items():
        print(f"{key}: {value}")
    
    # 3. 显示第一个样本的前5轮对话
    print("\n=== 样本 0 前5轮对话 ===")
    turns = dataset.get_dialogue_turns(0)[:5]
    for turn in turns:
        print(f"[Session {turn.session_id}] {turn.speaker}: {turn.text}")
    
    # 4. 搜索包含"Caroline"的问答对
    print("\n=== 包含'Caroline'的问答对 ===")
    caroline_qa = dataset.search_qa_by_keyword("Caroline", 0)[:3]
    for sample_id, qa in caroline_qa:
        print(f"Q: {qa.question}")
        print(f"A: {qa.answer}")
        print(f"Evidence: {qa.evidence}")
        print(f"Category: {qa.category}")
        print("-" * 50)
    
    # 5. 车载适用性分析
    print("\n=== 车载适用性分析 ===")
    car_analysis = dataset.analyze_car_suitability()
    
    print("各样本车载适用性评分:")
    for sample_name, data in car_analysis.items():
        print(f"{sample_name}:")
        print(f"  总对话轮次: {data['total_turns']}")
        print(f"  车载相关内容: {data['car_related']}次 ({data['car_ratio']:.1%})")
        print(f"  医疗相关内容: {data['medical_content']}次 ({data['medical_ratio']:.1%})")
        print(f"  复杂学习内容: {data['complex_content']}次 ({data['complex_ratio']:.1%})")
        print(f"  适用性评分: {data['suitability_score']:.2f}")
        print(f"  推荐: {data['recommendation']}")
        print()
    
    # 找出最推荐的样本
    recommended_samples = []
    for sample_name, data in car_analysis.items():
        if data['recommendation'] == '推荐':
            recommended_samples.append((sample_name, data['suitability_score']))
    
    recommended_samples.sort(key=lambda x: x[1], reverse=True)
    
    print("=== 车端大模型测试推荐样本 ===")
    if recommended_samples:
        for i, (sample_name, score) in enumerate(recommended_samples, 1):
            print(f"{i}. {sample_name} (评分: {score:.2f})")
    else:
        print("没有找到高度推荐的样本")
    
    # 6. 导出数据到CSV
    print("\n=== 导出数据 ===")
    dataset.export_to_csv()
    
    # 7. 可视化统计信息
    print("\n=== 生成可视化图表 ===")
    dataset.visualize_statistics()
    
    print("\n=== 分析完成 ===")


if __name__ == "__main__":
    main()
