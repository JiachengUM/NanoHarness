# 数据文件说明文档

## 文件结构

`sample_202601.csv` 和 `sample_202602.csv` 文件包含了用户与车载系统交互的对话数据，两个文件的字段结构完全相同。

## 字段说明

| 序号 | 字段名称 | 含义 | 取值范围 | 示例 |
|------|---------|------|---------|------|
| 1 | 用户ID | 唯一标识用户的ID | 数字字符串 | 1028061009 |
| 2 | 时间戳 | 交互发生的时间 | 格式：YYYYMMDD HH:MM:SS | 20260102 09:27:38 |
| 3 | 设备ID | 车辆或设备的唯一标识 | 十六进制字符串 | 0x1007224997305356288 |
| 4 | 会话ID | 本次对话的唯一标识 | 字符串 | AA95F5DB7F64E28BC499E77C7B3DC3E5\|0 |
| 5 | 版本号 | 系统版本信息 | 字符串 | 7.5.5.2025_1030_2130 |
| 6 | 设备标识 | 设备的唯一标识 | 字符串 | 3859ba3f659456cf5e81ac18561bf4f8cb23a1a002ee527c242f442e98dc8b42 |
| 7 | 类型标识 | 指令类型标识 | 0, 1, 2, 3 | 0 |
| 8 | 用户指令 | 用户的语音或文本输入 | 字符串 | 听隐形的翅膀 |
| 9 | 系统回应 | 系统的回应内容 | 字符串 | OK |
| 10 | 功能类别 | 交互的功能类别 | music, navi, carControl, systemControl, mediaControl, naviControl, generalControl, aiqa, nluMocked, autoPilot, relaxCapsule, carInfo, windowControl, video | music |
| 11 | 具体功能 | 具体的功能名称 | 对应功能类别的具体功能 | SearchMusic |
| 12 | 参数JSON | 功能相关的参数，JSON格式 | JSON字符串 | "[{\"name\":\"songName\",\"value\":\"隐形的翅膀\",\"normalizedValue\":\"隐形的翅膀\"},{\"name\":\"action\",\"value\":\"listen\",\"normalizedValue\":\"listen\"}]" |
| 13 | 对话ID | 对话的唯一标识 | UUID | eb274da3-4dd2-46d5-9193-89bedd7e9caa |
| 14 | 是否需要确认 | 系统是否需要用户确认 | true, false | false |
| 15 | 状态码 | 执行状态码 | -2, -1, 0, 1, 7 | -1 |
| 16 | 日期 | 交互发生的日期 | 格式：YYYYMMDD | 20260102 |

## 字段详细说明

### 功能类别（第10列）

| 功能类别 | 描述 |
|---------|------|
| music | 音乐相关功能 |
| navi | 导航相关功能 |
| carControl | 车辆控制功能 |
| systemControl | 系统控制功能 |
| mediaControl | 媒体控制功能 |
| naviControl | 导航控制功能 |
| generalControl | 通用控制功能 |
| aiqa | 智能问答功能 |
| nluMocked | 自然语言理解模拟 |
| autoPilot | 自动驾驶相关功能 |
| relaxCapsule | 放松模式功能 |
| carInfo | 车辆信息查询 |
| windowControl | 窗口控制功能 |
| video | 视频相关功能 |

### 状态码（第15列）

| 状态码 | 含义 |
|-------|------|
| -2 | 操作成功或已完成 |
| -1 | 操作进行中或需要进一步操作 |
| 0 | 操作失败或无结果 |
| 1 | 操作需要用户确认 |
| 7 | 特殊状态或其他状态 |

## 数据读取代码

### Python 代码

```python
import csv
import json


def read_sample_file(file_path):
   """
   读取样本CSV文件并解析数据
   
   Args:
       file_path: CSV文件路径
   
   Returns:
       list: 解析后的数据列表
   """
   data = []
   with open(file_path, 'r', encoding='utf-8') as f:
      reader = csv.reader(f, delimiter='\t')
      for row in reader:
         # 解析每一行数据
         record = {
            'user_id': row[0],
            'timestamp': row[1],
            'device_id': row[2],
            'session_id': row[3],
            'version': row[4],
            'device_identifier': row[5],
            'type_identifier': int(row[6]),
            'user_command': row[7],
            'system_response': row[8],
            'function_category': row[9],
            'specific_function': row[10],
            'parameters': json.loads(row[11]) if row[11] else [],
            'dialog_id': row[12],
            'needs_confirmation': row[13].lower() == 'true',
            'status_code': int(row[14]),
            'date': row[15]
         }
         data.append(record)
   return data


# 示例用法
if __name__ == "__main__":
   # 读取202601的数据
   data_202601 = read_sample_file('../../../sample_202601.csv')
   print(f"202601数据条数: {len(data_202601)}")

   # 读取202602的数据
   data_202602 = read_sample_file('../../../sample_202602.csv')
   print(f"202602数据条数: {len(data_202602)}")

   # 打印第一条数据示例
   if data_202601:
      print("\n第一条数据示例:")
      for key, value in data_202601[0].items():
         print(f"{key}: {value}")
```

### JavaScript 代码

```javascript
const fs = require('fs');
const path = require('path');

function readSampleFile(filePath) {
    /**
     * 读取样本CSV文件并解析数据
     * 
     * @param {string} filePath - CSV文件路径
     * @returns {Array} 解析后的数据列表
     */
    const data = [];
    const content = fs.readFileSync(filePath, 'utf8');
    const lines = content.split('\n');
    
    for (const line of lines) {
        if (line.trim() === '') continue;
        
        const row = line.split('\t');
        const record = {
            user_id: row[0],
            timestamp: row[1],
            device_id: row[2],
            session_id: row[3],
            version: row[4],
            device_identifier: row[5],
            type_identifier: parseInt(row[6]),
            user_command: row[7],
            system_response: row[8],
            function_category: row[9],
            specific_function: row[10],
            parameters: row[11] ? JSON.parse(row[11]) : [],
            dialog_id: row[12],
            needs_confirmation: row[13].toLowerCase() === 'true',
            status_code: parseInt(row[14]),
            date: row[15]
        };
        data.push(record);
    }
    
    return data;
}

// 示例用法
if (require.main === module) {
    // 读取202601的数据
    const data202601 = readSampleFile('sample_202601.csv');
    console.log(`202601数据条数: ${data202601.length}`);
    
    // 读取202602的数据
    const data202602 = readSampleFile('sample_202602.csv');
    console.log(`202602数据条数: ${data202602.length}`);
    
    // 打印第一条数据示例
    if (data202601.length > 0) {
        console.log('\n第一条数据示例:');
        console.log(data202601[0]);
    }
}
```

## 数据使用建议

1. **数据清洗**：在使用数据前，建议检查并处理可能的空值或异常值。
2. **数据分析**：可以从以下角度分析数据：
   - 用户使用频率最高的功能类别
   - 不同时间段的用户交互模式
   - 系统回应的成功率
   - 不同功能类别的使用场景
3. **数据可视化**：可以使用图表展示用户交互趋势、功能使用分布等。
4. **模型训练**：如果需要训练自然语言处理模型，这些数据可以作为训练集或验证集。

## 注意事项

1. 数据中的参数JSON字段可能包含复杂的嵌套结构，使用时需要注意解析。
2. 时间戳和日期字段可以用于时间序列分析。
3. 设备ID和用户ID可以用于用户行为分析和设备使用情况分析。
4. 状态码字段可以用于评估系统响应的有效性。

## 如何判断单轮对话和多轮对话

要判断文件中的用户指令字段所指向的是单轮对话还是多轮对话，可以通过以下几个字段的组合分析：

### 关键判断字段

1. **会话ID（第4列）**：同一个会话ID通常表示一个完整的对话过程，可能包含多轮交互。
2. **对话ID（第13列）**：对话ID通常是唯一的，每个具体的用户指令都有一个对应的对话ID。但通过观察数据，可以发现对话ID可能会有后缀（如`_2`、`_3`等），这些通常表示同一对话的不同轮次。
3. **时间戳（第2列）**：通过时间戳可以判断交互的时间顺序，同一会话中时间相近的指令可能属于同一多轮对话。
4. **功能类别和具体功能（第10、11列）**：连续的、相关的功能操作可能属于同一多轮对话。

### 判断方法

- **单轮对话**：会话ID下只有一个对话ID，或者对话ID没有后缀。
- **多轮对话**：同一会话ID下有多个对话ID，且这些对话ID可能有数字后缀，或者时间戳相近且功能相关。

### 示例分析

观察数据中，同一会话ID下如果有多个连续的用户指令，且对话ID有递增的后缀（如`c31741da-b983-458c-b2f7-c2bfd69f9d2d`、`c31741da-b983-458c-b2f7-c2bfd69f9d2d_3`、`c31741da-b983-458c-b2f7-c2bfd69f9d2d_5`等），则通常属于同一多轮对话。

### 实现代码

可以通过以下Python代码来识别多轮对话：

```python
def identify_dialog_turns(data):
    """
    识别对话轮次
    """
    # 按会话ID分组
    sessions = {}
    for record in data:
        session_id = record['session_id']
        if session_id not in sessions:
            sessions[session_id] = []
        sessions[session_id].append(record)
    
    # 分析每个会话
    for session_id, records in sessions.items():
        # 按时间戳排序
        records.sort(key=lambda x: x['timestamp'])
        
        # 分析对话ID模式
        dialog_ids = [r['dialog_id'] for r in records]
        base_dialog_ids = [id.split('_')[0] for id in dialog_ids]
        
        # 统计每个基础对话ID的出现次数
        from collections import Counter
        dialog_counts = Counter(base_dialog_ids)
        
        # 识别多轮对话
        multi_turn_dialogs = [dialog_id for dialog_id, count in dialog_counts.items() if count > 1]
        
        if multi_turn_dialogs:
            print(f"会话 {session_id} 包含多轮对话: {multi_turn_dialogs}")
        else:
            print(f"会话 {session_id} 只包含单轮对话")
```

通过这种方法，你可以有效地识别数据中的单轮和多轮对话模式。