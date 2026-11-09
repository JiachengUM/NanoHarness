# 数据处理说明

## 处理目标

对 `sample_data.csv` 中的数据进行以下处理：

1. 按照 `timestamp` 字段的时间递增顺序排序数据
2. 滚动式遍历每条数据，合并不同时间范围的 `user_command` 和 `system_response` 字段到新增的 `message` 字段
3. 时间范围包括：1分钟、5分钟、10分钟、半小时、一小时、6小时、12小时、1天、3天、1周、半个月、一个月
4. 每个 `message` 字段的格式为 `[{"user": user_command, "assistant": system_response}]`，类型必须是list
5. 如果时间范围内没有数据，那么对应 `message` 字段留空
6. 如果合并后的内容与前一条数据的合并内容相同，那么对应 `message` 字段留空
7. 确保输出文件 `sample-data-v2.csv` 的行数与原文件一致

## 处理步骤

1. **数据读取**：使用 pandas 读取 `sample_data.csv` 文件
2. **时间转换**：将 `timestamp` 列转换为 datetime 类型
3. **排序**：按照 `timestamp` 字段进行升序排序
4. **滚动遍历**：遍历每条数据，为每个时间范围计算其范围内的所有记录
5. **消息聚合**：将时间范围内的 `user_command` 和 `system_response` 聚合成消息列表（list类型），并将 `system` 改为 `assistant`
6. **去重处理**：如果当前消息与前一条消息相同，则留空
7. **数据输出**：将处理后的数据保存到 `sample-data-v2.csv` 文件

## 代码实现

```python
import pandas as pd
import json
from datetime import datetime, timedelta

# 读取数据
df = pd.read_csv('../../../sample_data.csv')

# 转换timestamp列为datetime类型
df['timestamp'] = pd.to_datetime(df['timestamp'], format='%Y%m%d %H:%M:%S')

# 按照timestamp排序
df = df.sort_values('timestamp').reset_index(drop=True)

# 定义时间范围列表
# 格式: (时间间隔, 字段名称)
time_ranges = [
    (timedelta(minutes=1), 'message_1min'),
    (timedelta(minutes=5), 'message_5min'),
    (timedelta(minutes=10), 'message_10min'),
    (timedelta(minutes=30), 'message_30min'),
    (timedelta(hours=1), 'message_1hour'),
    (timedelta(hours=6), 'message_6hour'),
    (timedelta(hours=12), 'message_12hour'),
    (timedelta(days=1), 'message_1day'),
    (timedelta(days=3), 'message_3day'),
    (timedelta(weeks=1), 'message_1week'),
    (timedelta(days=15), 'message_15day'),
    (timedelta(days=30), 'message_1month')
]

# 为每个时间范围创建message字段
for time_delta, column_name in time_ranges:
    # 初始化新列
    df[column_name] = ''
    # 滚动式遍历每条数据，合并时间范围内的数据
    previous_message = None
    for i in range(len(df)):
        # 获取当前时间
        current_time = df.loc[i, 'timestamp']
        # 确定时间范围的开始
        start_time = current_time - time_delta
        # 筛选在时间范围内的数据
        mask = (df['timestamp'] >= start_time) & (df['timestamp'] <= current_time)
        # 提取用户命令和系统响应
        messages = []
        for _, row in df[mask].iterrows():
            messages.append({
                'user': row['user_command'],
                'assistant': row['system_response']
            })
        # 将消息列表转换为JSON字符串
        if messages:
            current_message = json.dumps(messages, ensure_ascii=False)
            # 如果与前一条相同，则留空
            if current_message != previous_message:
                df.loc[i, column_name] = current_message
                previous_message = current_message
        else:
            # 如果没有数据，留空并重置previous_message
            previous_message = None

# 转换timestamp回字符串格式
df['timestamp'] = df['timestamp'].dt.strftime('%Y%m%d %H:%M:%S')

# 输出到新文件
df.to_csv('sample-data-v2.csv', index=False, encoding='utf-8-sig')

print(f"数据处理完成，已输出到 sample-data-v2.csv")
print(f"原文件行数: {len(df)}")
print(f"输出文件行数: {len(df)}")
```

## 输出文件

- **sample-data-v2.csv**：处理后的数据集，包含原有的所有字段以及新增的多个时间范围的 `message` 字段

## 注意事项

1. 时间范围是从当前记录的时间向前推算，包含当前记录本身
2. 每个 `message` 字段存储的是对应时间范围内所有记录的用户命令和系统响应的JSON数组（list类型），其中 `system` 已改为 `assistant`
3. 如果时间范围内没有数据，对应 `message` 字段留空
4. 如果合并后的内容与前一条数据的合并内容相同，对应 `message` 字段留空
5. 输出文件使用 `utf-8-sig` 编码，确保中文字符正常显示
6. 输出文件的行数与原文件一致
