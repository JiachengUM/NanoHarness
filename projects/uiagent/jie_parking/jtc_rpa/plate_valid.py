import re


def validate_license_plate(text):
    """
    校验文本是否为有效的车牌号
    支持普通车牌、新能源车牌、武警车牌、军车车牌等格式

    Args:
        text (str): 待校验的文本

    Returns:
        bool: 是否为有效的车牌号
    """
    if not text or not isinstance(text, str):
        return False

    # 去除空格并转换为大写
    text = text.strip().upper()

    # 长度校验：根据不同车牌类型验证长度
    # 普通车牌：7位（省份简称 + 字母 + 5位数字/字母）
    # 新能源车牌：8位（省份简称 + 字母 + [D/F] + 5位数字/字母）
    # 武警车牌：6位或7位（WJ + 省份代码 + 4或5位数字）
    # 军车车牌：6-7位（省份简称 + 字母 + 4-5位数字）
    if len(text) < 5 or len(text) > 8:
        return False

    # 普通车牌格式：省份简称 + 字母 + 5位数字/字母组合 (总共7位)
    # 新能源车牌格式：省份简称 + 字母 + 6位数字/字母组合（D/E开头为纯电动，F开头为混动）(总共8位)
    # 武警车牌：WJ + 省份代码 + 4-5位数字
    # 军车车牌：省份简称 + 字母 + 4-5位数字

    patterns = [
        # 普通车牌：例如 京A12345 (省份简称 + 字母 + 5位数字/字母，总共7位字符)
        r'^[京津沪渝冀豫云辽黑湘皖鲁新苏浙赣鄂桂甘晋蒙陕吉闽贵粤青藏川宁琼使领][A-HJ-NP-Z][A-HJ-NP-Z0-9]{5}$',

        # 新能源车牌：例如 京AD12345, 京AF12345 (省份简称 + 字母 + [D/F] + 5位数字/字母，总共8位字符)
        r'^[京津沪渝冀豫云辽黑湘皖鲁新苏浙赣鄂桂甘晋蒙陕吉闽贵粤青藏川宁琼使领][A-HJ-NP-Z][DF][A-HJ-NP-Z0-9]{5}$',

        # 武警车牌：例如 WJ京1234 (WJ + 省份代码 + 4位数字，总共6位字符)
        r'^WJ[京津沪渝冀豫云辽黑湘皖鲁新苏浙赣鄂桂甘晋蒙陕吉闽贵粤青藏川宁琼][0-9]{4}$',

        # 武警车牌扩展：例如 WJ京12345 (WJ + 省份代码 + 5位数字，总共7位字符)
        r'^WJ[京津沪渝冀豫云辽黑湘皖鲁新苏浙赣鄂桂甘晋蒙陕吉闽贵粤青藏川宁琼][0-9]{5}$',

        # 军车车牌：例如 京V12345 或 京V1234 (省份简称 + 字母 + 4-5位数字，总共6-7位字符)
        r'^[京津沪渝冀豫云辽黑湘皖鲁新苏浙赣鄂桂甘晋蒙陕吉闽贵粤青藏川宁琼][A-HJ-NP-Z][0-9]{4,5}$',
    ]

    return any(re.match(pattern, text) for pattern in patterns)


def test_license_plate_validation():
    """测试车牌号校验方法"""
    test_cases = [
        # 有效车牌
        {"input": "京A12345", "expected": True},
        {"input": "京AD12345", "expected": True},  # 新能源车牌
        {"input": "京AF12345", "expected": True},  # 新能源车牌
        {"input": "WJ京1234", "expected": True},  # 武警车牌
        {"input": "WJ京12345", "expected": True},  # 武警车牌扩展
        {"input": "沪B56789", "expected": True},
        {"input": "粤B12345", "expected": True},  # 军车车牌

        # 无效车牌
        {"input": "", "expected": False},
        {"input": "123456", "expected": False},
        {"input": "京12345", "expected": False},
        {"input": "A12345", "expected": False},
        {"input": "京A1234", "expected": False},  # 长度不够，应为7位
        {"input": "京A123456", "expected": False},  # 长度过长
        {"input": "ZZ99999", "expected": False},
        {"input": "京A123456", "expected": False},  # 普通车牌超过5位
        {"input": "京AA12345", "expected": False},  # 普通车牌格式错误
        {"input": "京A123", "expected": False},  # 长度太短
        {"input": "京A1234567", "expected": False},  # 长度太长
    ]

    print("车牌号校验测试结果：")
    all_passed = True

    for index, test_case in enumerate(test_cases):
        result = validate_license_plate(test_case["input"])
        passed = result == test_case["expected"]
        status = '✓' if passed else '✗'
        print(f"测试 {index + 1}: \"{test_case['input']}\" -> {result} {status}")
        if not passed:
            all_passed = False

    print(f"\n总体结果: {'全部通过' if all_passed else '存在失败'}")
    return all_passed


# 运行测试
if __name__ == "__main__":
    test_license_plate_validation()



