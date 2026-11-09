# API工具开发技能

## 技能描述

本技能用于将API接口文档转换为LangChain BaseTool工具类，并生成完整的测试用例。适用于将第三方API接口封装为可复用的工具组件。

## 适用场景

- 需要将第三方API接口封装为LangChain BaseTool
- 需要为API接口创建详细的README文档
- 需要为API工具创建完整的测试用例
- 需要分析API的原子能力并进行模块化设计

## 执行步骤

### 第一步：分析API接口文档

**输入**：API接口文档（包含接口地址、参数、返回字段等）

**分析要点**：
1. 识别接口的基础信息（URL、请求方式、认证方式）
2. 识别所有原子能力（不同的搜索类型、操作类型等）
3. 分析每个原子能力的输入参数
4. 分析每个原子能力的输出字段
5. 识别调用方式（通过哪些参数区分不同能力）

**输出**：原子能力清单，包含每个能力的调用参数和返回字段

### 第二步：创建README文档

**文档结构**：
```markdown
# {API名称}接口文档

## 接口概述
- 接口地址
- 命令字
- 请求方式
- 返回格式

## 认证参数
- 列出所有认证参数

## 原子能力分析
### 1. {能力名称}
- 功能描述
- 调用方式（URL参数）
- 输入参数表格
- 输出字段表格
- 使用场景

## 通用返回字段
- 所有能力共有的返回字段

## 错误码说明
- 错误码对照表

## 调用示例
- 每个原子能力的调用示例

## 注意事项
- 限制条件
- 特殊处理要求
```

**保存位置**：`{项目目录}/toolset/{API名称}README.md`

### 第三步：创建Python工具类

**文件结构**：
```python
import hashlib
import json
import logging
import time
import asyncio
from dataclasses import dataclass, field as dc_field
from enum import Enum
from typing import List, Optional

import aiohttp
from pydantic import BaseModel, Field

from aicore.tools import BaseTool

__all__ = [
    "{Ability1}Input",
    "{Ability1}Tool",
    "{Ability2}Input",
    "{Ability2}Tool",
]

logger = logging.getLogger(__name__)

# 认证和请求函数
def _sign_function(params: dict, app_key: str) -> str:
    """生成签名"""
    pass

async def _request_function(opi_cmd: str, additional: dict) -> Optional[dict]:
    """发送API请求"""
    pass

# 数据模型
class Status(str, Enum):
    SUCCESS = "success"
    ERROR = "error"

@dataclass(slots=True, frozen=True)
class ItemModel:
    """数据项模型"""
    pass

# 输入输出模型
class AbilityInput(BaseModel):
    """输入参数模型"""
    pass

class AbilityOutput(BaseModel):
    """输出结果模型"""
    pass

# 工具类
class AbilityTool(BaseTool):
    name: str = "{ability_name}"
    description: str = "{工具描述}"
    args_schema: type[BaseModel] = AbilityInput

    def _run(self, *args, **kwargs) -> dict:
        raise NotImplementedError("请使用异步调用 ainvoke/astream")

    async def _arun(self, *args, **kwargs) -> AbilityOutput:
        """异步执行"""
        pass
```

**设计原则**：
1. 每个原子能力对应一个独立的Tool类
2. 使用Pydantic进行输入输出验证
3. 使用dataclass定义数据模型
4. 实现异步执行方法
5. 完善的错误处理和日志记录

**保存位置**：`{项目目录}/toolset/{api_name}.py`

### 第四步：创建测试用例

**测试文件结构**：
```python
import asyncio
from rich import print

from projects.mind.toolset.{api_name} import (
    {Ability1}Tool,
    {Ability2}Tool,
)

async def test_ability1():
    """测试能力1"""
    tool = {Ability1}Tool()
    test_cases = [
        # 测试用例列表
    ]
    for test_case in test_cases:
        result = await tool.ainvoke(test_case)
        # 验证结果

async def test_edge_cases():
    """测试边界情况"""
    pass

async def test_special_cases():
    """测试特殊情况"""
    pass

async def main():
    """运行所有测试"""
    pass

if __name__ == "__main__":
    asyncio.run(main())
```

**测试覆盖范围**：
1. **功能测试**：每个原子能力的正常功能
2. **分页测试**：验证分页功能
3. **边界测试**：空输入、超出范围、无效参数
4. **特殊字符测试**：特殊字符处理
5. **综合测试**：所有能力的整体可用性

**保存位置**：`{项目目录}/toolset/tests/test_{api_name}.py`

### 第五步：创建测试用例说明文档

**文档结构**：
```markdown
# {API名称}测试用例说明

## 测试文件
- 测试脚本
- 工具模块
- README文档

## 测试场景分类
### 1. {测试场景名称}
- 测试目的
- 测试用例表格
- 验证点

## 运行测试
- 运行所有测试的命令
- 运行单个测试的方法

## 预期输出格式
- 成功输出示例
- 错误输出示例

## 测试覆盖范围
- 功能覆盖
- 输入验证
- 输出验证
- 异常处理

## 测试注意事项
- 配置要求
- 环境要求
- 限制条件

## 扩展测试建议
```

**保存位置**：`{项目目录}/toolset/tests/{API名称}测试用例.md`

## 输入模板

### 用户输入示例

```
请分析以下API接口文档，并完成以下任务：

1. 分析接口的原子能力，详细说明通过哪些参数或URL来调用原子能力
2. 创建详细的README文档，放入指定目录
3. 根据README文档，将接口原子能力封装为LangChain BaseTool工具类
4. 为工具类创建完整的测试用例和测试代码

接口文档如下：
{API接口文档内容}
```

### 关键信息提取

从API文档中提取以下信息：

1. **基础信息**
   - 接口地址
   - 请求方式（GET/POST）
   - 认证方式
   - 签名算法

2. **原子能力识别**
   - 通过哪些参数区分不同能力
   - 每个能力的参数值
   - 每个能力的功能描述

3. **参数分析**
   - 必传参数
   - 可选参数
   - 参数类型
   - 默认值
   - 限制条件

4. **返回字段分析**
   - 字段名称
   - 字段类型
   - 字段说明
   - 权限影响

## 输出模板

### README文档模板

使用Markdown格式，包含：
- 接口概述
- 认证参数
- 原子能力分析（每个能力独立章节）
- 通用返回字段
- 错误码说明
- 调用示例
- 注意事项

### Python工具类模板

遵循以下规范：
- 使用异步编程
- 继承BaseTool
- 使用Pydantic验证
- 完善的错误处理
- 详细的日志记录

### 测试用例模板

包含以下测试类型：
- 功能测试
- 分页测试
- 边界测试
- 特殊字符测试
- 综合测试

## 最佳实践

### 1. 原子能力设计

- **单一职责**：每个工具类只负责一个原子能力
- **明确命名**：工具名称清晰表达其功能
- **完整描述**：description字段详细说明工具用途

### 2. 数据模型设计

- **类型安全**：使用Pydantic进行类型验证
- **默认值**：为可选参数提供合理默认值
- **文档化**：为每个字段添加description

### 3. 错误处理

- **统一格式**：使用统一的错误响应格式
- **详细日志**：记录足够的调试信息
- **用户友好**：错误信息对用户友好

### 4. 测试设计

- **覆盖全面**：覆盖正常、异常、边界情况
- **独立运行**：每个测试可以独立运行
- **清晰输出**：测试结果清晰易读

### 5. 文档维护

- **保持同步**：代码变更时同步更新文档
- **示例完整**：提供可运行的代码示例
- **版本管理**：记录API版本变更

## 常见问题

### Q1: 如何识别API的原子能力？

A: 查找API文档中通过参数区分的不同功能类型，例如：
- 通过`type`参数区分搜索类型
- 通过`action`参数区分操作类型
- 通过不同的URL路径区分功能

### Q2: 如何处理API认证？

A: 根据API文档实现相应的认证方式：
- 签名认证：实现签名生成函数
- Token认证：在请求头中添加Token
- API Key认证：在参数中添加API Key

### Q3: 如何设计测试用例？

A: 遵循以下原则：
- 正常功能测试：验证基本功能
- 边界测试：测试极限情况
- 异常测试：验证错误处理
- 集成测试：测试整体流程

### Q4: 如何处理API返回的错误？

A: 统一错误处理流程：
1. 检查返回码
2. 解析错误信息
3. 返回统一的错误格式
4. 记录详细日志

## 示例参考

参考本次任务中的QQ音乐搜索接口实现：
- README文档：`QQ音乐搜索接口README.md`
- 工具类：`qq_music_search.py`
- 测试代码：`test_qq_music_search.py`
- 测试说明：`QQ音乐搜索工具测试用例.md`

## 扩展建议

1. **性能优化**：添加缓存机制，减少重复请求
2. **重试机制**：实现自动重试，提高可靠性
3. **限流控制**：添加请求限流，避免超限
4. **监控告警**：添加监控指标，及时发现问题
5. **版本兼容**：支持多版本API，提高兼容性

## 总结

本技能提供了一套完整的API工具开发流程，从文档分析到工具实现，再到测试验证，确保开发出高质量、可复用的API工具组件。
