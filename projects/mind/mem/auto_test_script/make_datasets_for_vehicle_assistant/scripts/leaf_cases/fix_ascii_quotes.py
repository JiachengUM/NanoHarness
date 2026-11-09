"""鲁棒修复脚本：扫描 JSON 文件，对字符串值内部未转义的 ASCII 双引号转义为 \\"。

策略：
- 逐字符扫描整个文件
- 跟踪状态：在字符串内 / 在字符串外
- 字符串以 " 开头，遇到下一个未转义的 " 结束
- 但实际问题是：字符串内部的 " 被误用为中文引号
- 我们识别：一个 " 如果后面紧跟的是 JSON 结构字符（, : ] } 空白 换行），则视为字符串结束符
- 否则视为字符串内部的误用引号，转义为 \"
"""
import sys
from pathlib import Path


def is_json_struct_char(ch: str) -> bool:
    return ch in ',:]}\n\r\t '


def fix(content: str) -> str:
    out = []
    i = 0
    n = len(content)
    in_string = False
    while i < n:
        ch = content[i]
        if not in_string:
            out.append(ch)
            if ch == '"':
                in_string = True
            i += 1
            continue

        # in_string == True
        if ch == '\\':
            # 转义序列，原样保留两个字符
            out.append(ch)
            if i + 1 < n:
                out.append(content[i + 1])
                i += 2
            else:
                i += 1
            continue

        if ch == '"':
            # 判断这个 " 是字符串结束符还是内部的误用引号
            # 向后看跳过空白，看下一个非空白字符
            j = i + 1
            while j < n and content[j] in ' \t':
                j += 1
            if j >= n or is_json_struct_char(content[j]):
                # 字符串结束符
                out.append('"')
                in_string = False
                i += 1
            else:
                # 内部误用引号，转义
                out.append('\\"')
                i += 1
            continue

        out.append(ch)
        i += 1

    return ''.join(out)


def main(path: str) -> None:
    p = Path(path)
    content = p.read_text(encoding="utf-8")
    fixed_content = fix(content)
    p.write_text(fixed_content, encoding="utf-8")
    print(f"[OK] 已修复 {path}")


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "artifacts/projects/benz_project/cases/vehicle_assistant_cases.json"
    main(path)
