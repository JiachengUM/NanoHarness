# LOCOMO 数据集分析报告

## 数据集概览

### 基本信息
- **总样本数**: 10个
- **总问答对数**: 1,986个
- **总会话数**: 272个
- **总对话轮次**: 5,882轮
- **说话者数量**: 18个

### 说话者列表
Caroline, Melanie, John, Nate, Tim, Audrey, Andrew, Sam, Joanna, James, Deborah, Dave, Evan, Gina, Maria, Jon, Jolene, Calvin

## 问答类别分布 (更新定义)

| 类别 | 问题数量 | 占比 | 说明 |
|------|----------|------|------|
| 类别 1 | 282个 | 14.2% | **Single-hop** (单跳推理) |
| 类别 2 | 321个 | 16.2% | **Multi-hop** (多跳推理) |
| 类别 3 | 96个 | 4.8% | **Temporal reasoning** (时间推理) |
| 类别 4 | 841个 | 42.3% | **Open-domain knowledge** (开放域知识) |
| 类别 5 | 446个 | 22.5% | **Adversarial** (对抗性测试) |

## 类别详细说明

### 类别 1: Single-hop (单跳推理)
- **定义**: 直接从对话中提取单一信息点的问题
- **特点**: 答案通常在一个对话轮次中直接给出
- **示例**: 
  - 问题: "What did Caroline research?"
  - 答案: "Adoption agencies"
  - 证据: D2:8

### 类别 2: Multi-hop (多跳推理)
- **定义**: 需要结合多个对话片段进行推理的问题
- **特点**: 答案需要从不同会话或对话轮次中综合信息
- **示例**:
  - 问题: "When did Caroline go to the LGBTQ support group?"
  - 答案: "7 May 2023"
  - 证据: D1:3

### 类别 3: Temporal reasoning (时间推理)
- **定义**: 涉及时间顺序、时间关系和时序推理的问题
- **特点**: 需要理解事件的时间顺序和因果关系
- **示例**:
  - 问题: "What fields would Caroline be likely to pursue in her education?"
  - 答案: "Psychology, counseling certification"
  - 证据: D1:9, D1:11

### 类别 4: Open-domain knowledge (开放域知识)
- **定义**: 需要结合对话内容和外部知识的问题
- **特点**: 问题涉及广泛的知识领域，需要常识推理
- **示例**:
  - 问题: How does Melanie prioritize self-care?
  - 答案: by carving out some me-time each day for activities like running, reading, or playing the violin
  - 特点: 需要理解社会背景和常识

### 类别 5: Adversarial (对抗性测试)
- **定义**: 专门设计的对抗性测试问题
- **特点**: 包含对抗性答案，用于测试模型的鲁棒性
- **示例**:
  - 问题: "What did Caroline realize after her charity race?"
  - 对抗答案: "self-care is important"
  - 特点: 测试模型是否能抵抗误导性信息

## 车载适用性分析

### 分析概述
基于关键词匹配方法，对LOCOMO数据集的10个对话样本进行了车载场景适用性分析，识别适合车端大模型测试的对话内容。

### 关键词定义
- **车载相关关键词**: car, drive, road, travel, trip, music, food, work, family, kids, school, meeting, schedule
- **医疗相关关键词**: medical, doctor, hospital, surgery, treatment, diagnosis
- **复杂学习关键词**: study, learn, education, art, painting, technique

### 评分规则
适用性评分 = 车载相关比例 × 10 - 医疗相关比例 × 5 - 复杂学习比例 × 3

### 分析结果

| 样本 | 总对话轮次 | 车载相关内容 | 医疗相关内容 | 复杂学习内容 | 适用性评分 | 推荐等级 |
|------|------------|-------------|-------------|-------------|------------|----------|
| sample_0 | 419轮 | 220次 (52.5%) | 1次 (0.2%) | 107次 (25.5%) | 4.47 | 🟢 高度推荐 |
| sample_1 | 369轮 | 70次 (19.0%) | 0次 (0.0%) | 45次 (12.2%) | 1.53 | 🟡 推荐 |
| sample_2 | 663轮 | 189次 (28.5%) | 1次 (0.2%) | 85次 (12.8%) | 2.46 | 🟡 推荐 |
| sample_3 | 629轮 | 84次 (13.4%) | 0次 (0.0%) | 33次 (5.2%) | 1.18 | 🟡 推荐 |
| sample_4 | 680轮 | 154次 (22.6%) | 1次 (0.1%) | 66次 (9.7%) | 1.97 | 🟡 推荐 |
| sample_5 | 675轮 | 99次 (14.7%) | 0次 (0.0%) | 46次 (6.8%) | 1.26 | 🟡 推荐 |
| sample_6 | 689轮 | 125次 (18.1%) | 3次 (0.4%) | 74次 (10.7%) | 1.47 | 🟡 推荐 |
| sample_7 | 681轮 | 108次 (15.9%) | 0次 (0.0%) | 75次 (11.0%) | 1.26 | 🟡 推荐 |
| sample_8 | 509轮 | 111次 (21.8%) | 7次 (1.4%) | 80次 (15.7%) | 1.64 | 🟡 推荐 |
| sample_9 | 568轮 | 275次 (48.4%) | 0次 (0.0%) | 71次 (12.5%) | 4.47 | 🟢 高度推荐 |

### 车端大模型测试推荐样本

#### 🟢 高度推荐样本
1. **sample_0** (评分: 4.47) - Caroline & Melanie对话
   - 车载相关内容占比52.5%，医疗内容极少
   - 包含大量工作、家庭、旅行相关话题
   - 适合通勤和家庭出行场景

2. **sample_9** (评分: 4.47) - 另一个高评分样本
   - 车载相关内容占比48.4%，无医疗内容
   - 对话内容丰富，适合多种车载场景

### 应用建议

1. **优先使用**: sample_0 和 sample_9 进行车端大模型测试
2. **内容筛选**: 从推荐样本中筛选车载相关的对话片段
3. **安全考虑**: 避免使用包含医疗内容的对话
4. **复杂度控制**: 注意控制复杂学习内容的比例

## 生成的文件

### CSV 文件 (locomo_analysis/)
- `sample_X_dialogue.csv`: 每个样本的对话数据
- `sample_X_qa.csv`: 每个样本的问答对数据

### 可视化图表
- `locomo_statistics.png`: 数据集统计信息图表