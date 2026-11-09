"""
df_to_html 函数使用演示

这个文件展示了如何使用 df_to_html 函数来生成各种类型的HTML表格。
适合初学者学习如何将pandas DataFrame转换为美观的HTML表格。

主要功能：
1. 基础用法：最简单的表格生成
2. 枚举样式：使用预设的主题和样式
3. 混合样式：结合枚举和自定义样式
4. 数据格式化：自定义数据的显示格式

学习目标：
- 了解 df_to_html 函数的基本用法
- 学会使用不同的样式选项
- 掌握如何自定义数据格式化
- 理解如何生成美观的HTML表格
"""

# 导入必要的库
import pandas as pd
# 从nanoai工具包导入df_to_html函数和样式枚举
from nanoai.utils.text_utils import df_to_html, Theme, CellStyle


def create_simple_data():
    """
    创建简单的示例数据
    
    这个函数创建一个包含不同类型数据的pandas DataFrame：
    - 文本数据：普通字符串
    - 数字数据：整数和小数
    - 布尔数据：True和False值
    - 列表数据：包含不同类型元素的列表
    
    为什么要使用dtype=object？
    pandas默认会将Python原生类型转换为numpy类型，这会导致样式判断出现问题。
    使用dtype=object可以保持原生Python类型，让样式函数正常工作。
    """
    # 准备原始数据字典
    data = {
        '文本': ['短文本', '长文本测试', '包含换行符的\n文本'],  # 字符串列
        '数字': [123, 45.67, -89],                              # 数字列（整数和小数）
        '布尔值': [True, False, True],                          # 布尔列
        '列表': [[1, 2, 3], ['a', 'b'], [True, False]]         # 列表列
    }
    
    # 创建DataFrame，指定dtype=object保持原生Python类型
    df = pd.DataFrame(data, dtype=object)
    
    # 确保数值列和布尔列保持原生类型（双重保险）
    df['数字'] = df['数字'].astype(object)
    df['布尔值'] = df['布尔值'].astype(object)
    
    return df


def demo_basic(df):
    """
    演示基础用法 - 最简单的表格生成
    
    这是最基础的用法，只需要提供DataFrame和文件名即可。
    适合初学者快速上手，了解df_to_html的基本功能。
    
    参数说明：
    - df: 要转换的pandas DataFrame
    - "basic_demo.html": 输出的HTML文件名
    - title: HTML页面的标题
    - summary_info: 页面顶部的统计信息
    """
    print("1. 基础演示")
    
    # 调用df_to_html函数，使用最简单的参数
    df_to_html(
        df,                           # 要转换的DataFrame
        "basic_demo.html",            # 输出的HTML文件名
        title="🔍 基础演示",          # 页面标题
        summary_info={                # 页面顶部的统计信息
            "数据行数": str(len(df)),  # 显示数据行数
            "数据类型": "4种"          # 显示数据类型数量
        }
    )
    print("✅ 生成了 basic_demo.html")


def demo_enum(df):
    """
    演示枚举用法 - 使用预设的主题和样式
    
    这个演示展示了如何使用预设的枚举值来设置表格样式。
    枚举值的好处是类型安全，不容易出错，而且代码更易读。
    
    主要概念：
    - Theme: 预设的主题枚举（如GREEN, BLUE, PURPLE等）
    - CellStyle: 预设的单元格样式枚举（如SUCCESS, ERROR, INFO等）
    - cell_styler: 一个函数，根据数据值返回对应的样式
    """
    print("\n2. 枚举演示")
    
    # 定义样式函数 - 根据数据类型返回不同的样式
    def styler(val):
        """
        样式函数：根据数据值返回对应的样式枚举
        
        参数：
        - val: 单元格的值
        
        返回值：
        - CellStyle枚举值或None（使用默认样式）
        """
        if isinstance(val, bool):
            # 布尔值：True显示为成功样式（绿色），False显示为错误样式（红色）
            return CellStyle.SUCCESS if val else CellStyle.ERROR
        elif isinstance(val, (int, float)):
            # 数字：显示为信息样式（蓝色）
            return CellStyle.INFO
        elif isinstance(val, list):
            # 列表：显示为警告样式（黄色）
            return CellStyle.WARNING
        # 其他类型：使用中性样式（默认）
        return CellStyle.NEUTRAL
    
    # 调用df_to_html函数，使用枚举样式
    df_to_html(
        df,                           # 要转换的DataFrame
        "enum_demo.html",             # 输出的HTML文件名
        title="🎨 枚举演示",          # 页面标题
        styling={"theme": Theme.GREEN},  # 使用绿色主题
        cell_styler=styler,           # 使用自定义样式函数
        show_text_length=15,          # 文本超过15字符时截断
        summary_info={                # 页面顶部的统计信息
            "数据行数": str(len(df)),
            "样式类型": "枚举样式",
            "主题": "绿色主题"
        }
    )
    print("✅ 生成了 enum_demo.html")


def demo_mixed(df):
    """
    演示混合用法 - 结合枚举和自定义样式
    
    这个演示展示了如何混合使用枚举样式和自定义CSS类。
    当预设的枚举样式不够用时，可以返回自定义的CSS类字符串。
    
    混合使用的优势：
    - 大部分情况使用枚举，代码简洁
    - 特殊需求使用自定义CSS，灵活性高
    - 不需要了解太多HTML知识
    """
    print("\n3. 混合演示")
    
    # 定义混合样式函数 - 结合枚举和自定义CSS类
    def mixed_styler(val):
        """
        混合样式函数：结合枚举样式和自定义CSS类
        
        这个函数展示了如何灵活地设置样式：
        - 对于常见类型，使用预设的枚举样式
        - 对于特殊需求，返回自定义的CSS类字符串
        """
        if isinstance(val, bool):
            # 布尔值：True使用枚举样式，False使用自定义CSS类
            return CellStyle.SUCCESS if val else CellStyle.ERROR  # 改为使用枚举样式
        elif isinstance(val, (int, float)):
            # 数字：使用枚举样式
            return CellStyle.INFO
        elif isinstance(val, str) and len(val) > 10:
            # 长文本：使用自定义CSS类，但改为使用枚举样式
            return CellStyle.WARNING
        # 其他类型：使用中性样式
        return CellStyle.NEUTRAL
    
    # 调用df_to_html函数，使用混合样式
    df_to_html(
        df,                           # 要转换的DataFrame
        "mixed_demo.html",            # 输出的HTML文件名
        title="🎨 混合演示",          # 页面标题
        styling={"theme": Theme.PURPLE},  # 使用紫色主题
        cell_styler=mixed_styler,     # 使用混合样式函数
        show_text_length=12,          # 文本超过12字符时截断
        summary_info={                # 页面顶部的统计信息
            "数据行数": str(len(df)),
            "样式类型": "混合样式",
            "主题": "紫色主题"
        }
    )
    print("✅ 生成了 mixed_demo.html")


def demo_formatter(df):
    """
    演示格式化器用法 - 自定义数据格式化显示
    
    这个演示展示了如何使用cell_formatter参数来自定义数据的显示格式。
    格式化器可以将原始数据转换为更易读、更美观的形式。
    
    格式化器的优势：
    - 提高数据可读性
    - 添加视觉符号（emoji）
    - 统一数据格式
    - 突出重要信息
    """
    print("\n4. 格式化器演示")
    
    # 定义各种专门的格式化器函数
    
    def number_formatter(val):
        """
        数字格式化器：美化数字显示
        
        功能：
        - 整数：添加千位分隔符，如 1234 -> 1,234
        - 小数：保留两位小数，如 45.678 -> 45.68
        """
        if isinstance(val, (int, float)):
            if isinstance(val, int):
                return f"整数: {val:,}"  # 添加千位分隔符
            else:
                return f"小数: {val:.2f}"  # 保留两位小数
        return str(val)
    
    def bool_formatter(val):
        """
        布尔值格式化器：用符号表示布尔值
        
        功能：
        - True -> ✅ 是
        - False -> ❌ 否
        """
        if isinstance(val, bool):
            return "✅ 是" if val else "❌ 否"
        return str(val)
    
    def list_formatter(val):
        """
        列表格式化器：美化列表显示
        
        功能：
        - 显示列表长度
        - 将列表元素用逗号连接
        - 例如：[1,2,3] -> 列表(3项): 1, 2, 3
        """
        if isinstance(val, list):
            return f"列表({len(val)}项): {', '.join(map(str, val))}"
        return str(val)
    
    # 定义综合格式化器 - 根据数据类型调用对应的格式化器
    def cell_formatter(val):
        """
        综合格式化器：根据数据类型应用不同的格式化规则
        
        这个函数是格式化器的入口点，它会：
        1. 检查数据的类型
        2. 调用对应的专门格式化器
        3. 返回格式化后的字符串
        """
        if isinstance(val, bool):
            return bool_formatter(val)      # 布尔值格式化
        elif isinstance(val, (int, float)):
            return number_formatter(val)    # 数字格式化
        elif isinstance(val, list):
            return list_formatter(val)      # 列表格式化
        elif isinstance(val, str):
            return f"📝 {val}"              # 文本添加前缀
        return str(val)                     # 其他类型直接转字符串
    
    # 调用df_to_html函数，使用自定义格式化器
    df_to_html(
        df,                           # 要转换的DataFrame
        "formatter_demo.html",        # 输出的HTML文件名
        title="🔧 格式化器演示",      # 页面标题
        styling={"theme": Theme.BLUE}, # 使用蓝色主题
        cell_formatter=cell_formatter, # 使用自定义格式化器
        show_text_length=25,          # 文本超过25字符时截断
        summary_info={                # 页面顶部的统计信息
            "数据行数": str(len(df)),
            "格式化类型": "自定义格式化",
            "主题": "蓝色主题"
        }
    )
    print("✅ 生成了 formatter_demo.html")


def demo_df_to_html():
    """
    主演示函数 - 运行所有演示
    
    这个函数是演示的入口点，它会：
    1. 创建示例数据
    2. 依次运行四个不同的演示
    3. 显示总结信息
    
    学习建议：
    - 先运行整个演示，查看生成的HTML文件
    - 然后逐个函数学习，理解每个参数的作用
    - 尝试修改参数值，观察效果变化
    - 最后尝试创建自己的数据和样式
    """
    print("=== df_to_html 功能演示 ===")
    
    # 第一步：创建示例数据
    print("📊 创建示例数据...")
    df = create_simple_data()
    print(f"✅ 数据创建完成，包含 {len(df)} 行数据")
    
    # 第二步：依次运行各个演示
    print("\n🚀 开始运行演示...")
    demo_basic(df)      # 演示1：基础用法
    demo_enum(df)       # 演示2：枚举样式
    demo_mixed(df)      # 演示3：混合样式
    demo_formatter(df)  # 演示4：数据格式化
    
    # 第三步：显示总结信息
    print("\n" + "=" * 50)
    print("🎉 所有演示完成！")
    print("\n📁 生成的文件：")
    print("  - basic_demo.html (基础演示)")
    print("  - enum_demo.html (枚举演示)")
    print("  - mixed_demo.html (混合演示)")
    print("  - formatter_demo.html (格式化器演示)")
    
    print("\n💡 学习要点：")
    print("  1. 基础演示：最简单的用法，快速上手")
    print("  2. 枚举演示：使用预设主题和样式，代码简洁")
    print("  3. 混合演示：枚举和字符串结合，灵活性高")
    print("  4. 格式化器演示：自定义数据格式，提高可读性")
    
    print("\n🔧 进阶建议：")
    print("  - 尝试修改主题颜色（Theme.GREEN, Theme.BLUE等）")
    print("  - 自定义样式函数，添加更多数据类型判断")
    print("  - 创建自己的格式化器，美化特定类型的数据")
    print("  - 结合多个参数，创建复杂的表格样式")


if __name__ == "__main__":
    demo_df_to_html() 