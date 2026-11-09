import json

def rpa_func(param):
    import re
    def bounds_to_coordinates(bounds):
        """
        将bounds字符串转换为坐标点
        code: 0:成功  1是失败  2：结束流程
        """
        numbers = list(map(int, re.findall(r'\d+', bounds)))

        # 检查是否提取到了4个数字
        if len(numbers) != 4:
            return None
        # 构建字典
        result = {
            "x1": numbers[0],
            "y1": numbers[1],
            "x2": numbers[2],
            "y2": numbers[3]
        }
        return result

    def extract_license_plate(asr_text):
        """
        从ASR识别的文本中提取车牌号，处理同音字和大小写问题

        Args:
            asr_text (str): ASR识别的文本

        Returns:
            str or None: 提取到的车牌号，如果没有找到则返回None
        """

        # 省份简称映射表（处理同音字问题）
        province_map = {
            '京': '京', '津': '津', '沪': '沪', '渝': '渝', '冀': '冀', '豫': '豫',
            '云': '云', '辽': '辽', '黑': '黑', '湘': '湘', '皖': '皖', '鲁': '鲁',
            '新': '新', '苏': '苏', '浙': '浙', '赣': '赣', '鄂': '鄂', '桂': '桂',
            '甘': '甘', '晋': '晋', '蒙': '蒙', '陕': '陕', '吉': '吉', '闽': '闽',
            '贵': '贵', '粤': '粤', '青': '青', '藏': '藏', '川': '川', '宁': '宁',
            '琼': '琼',
            # 同音字映射
            '金': '京', '劲': '京', '经': '京', '井': '京',
            '津': '津', '今': '津', '进': '津',
            '胡': '沪', '虎': '沪', '护': '沪', '互': '沪',
            '雨': '渝', '鱼': '渝', '于': '渝', '余': '渝',
            '鸡': '冀', '机': '冀', '记': '冀', '继': '冀', '积': '冀',
            '预': '豫', '玉': '豫', '域': '豫', '遇': '豫', '育': '豫',
            '云': '云', '运': '云', '韵': '云',
            '林': '辽', '连': '辽', '联': '辽',
            '和': '黑', '赫': '黑', '贺': '黑', '合': '黑',
            '香': '湘', '乡': '湘', '相': '湘', '箱': '湘',
            '完': '皖', '皖': '皖', '碗': '皖', '晚': '皖',
            '鲁': '鲁', '路': '鲁', '露': '鲁', '录': '鲁',
            '新': '新', '心': '新', '辛': '新', '欣': '新',
            '苏': '苏', '素': '苏', '速': '苏', '诉': '苏',
            '浙': '浙', '者': '浙', '这': '浙', '遮': '浙',
            '赣': '赣', '敢': '赣', '感': '赣',
            '恶': '鄂', '饿': '鄂', '额': '鄂', '扼': '鄂',
            '归': '桂', '规': '桂', '鬼': '桂',  # 桂的同音字，不是贵
            '甘': '甘', '干': '甘', '赶': '甘',
            '晋': '晋', '仅': '晋', '进': '晋',
            '萌': '蒙', '盟': '蒙', '梦': '蒙',
            '陕': '陕', '善': '陕', '闪': '陕',
            '吉': '吉', '极': '吉', '级': '吉',
            '民': '闽', '敏': '闽', '名': '闽',
            '越': '粤', '阅': '粤', '约': '粤',
            '清': '青', '轻': '青', '倾': '青',
            '藏': '藏', '舱': '藏', '苍': '藏',
            '川': '川', '穿': '川', '传': '川',
            '宁': '宁', '凝': '宁', '拧': '宁',
            '穷': '琼', '穹': '琼', '琼': '琼',
        }

        # 预处理文本：去除空格和特殊字符，保留中文、字母、数字
        cleaned_text = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9]', '', asr_text)

        # 创建字母映射表
        letter_map = get_letter_mapping()

        # 特殊处理：处理复合字母（如"艾尔", "艾马", "艾克斯"等）
        # 首先处理复合字母，替换为单个字母
        processed_text = cleaned_text
        # 按长度排序，优先处理长的复合词
        sorted_compound_letters = sorted(
            [k for k, v in letter_map.items() if len(k) > 1],
            key=len,
            reverse=True
        )

        for compound in sorted_compound_letters:
            processed_text = processed_text.replace(compound, letter_map[compound])

        # 现在处理单字符映射
        result_text = ""
        i = 0
        while i < len(processed_text):
            char = processed_text[i]

            # 检查是否是省份字符
            if char in province_map:
                result_text += province_map[char]
            # 检查是否是字母字符
            elif char in letter_map and len(char) == 1:
                result_text += letter_map[char]
            # 否则直接添加
            else:
                result_text += char
            i += 1

        # 搜索可能的车牌号格式：省份(1个字符) + 字母(1个字符) + 数字/字母(5个字符)
        for i in range(len(result_text) - 6):
            potential_province = result_text[i]
            potential_second = result_text[i + 1]
            potential_end = result_text[i + 2:i + 7]

            # 检查是否符合车牌格式
            if (potential_province in ['京', '津', '沪', '渝', '冀', '豫', '云', '辽', '黑', '湘', '皖', '鲁',
                                       '新', '苏', '浙', '赣', '鄂', '桂', '甘', '晋', '蒙', '陕', '吉', '闽',
                                       '贵', '粤', '青', '藏', '川', '宁', '琼'] and
                    potential_second.isalpha() and
                    len(potential_end) == 5 and
                    all(c.isalnum() for c in potential_end)):

                result = f"{potential_province}{potential_second}{potential_end}"
                if is_valid_license_plate(result):
                    return result

        # 如果直接处理失败，尝试更宽松的模式匹配
        # 使用正则表达式匹配可能的车牌格式
        # 匹配模式：省份 + 字母 + 5位字母数字
        pattern = r'([京津沪渝冀豫云辽黑湘皖鲁新苏浙赣鄂桂甘晋蒙陕吉闽贵粤青藏川宁琼])([A-Z])([A-Z0-9]{5})'
        matches = re.findall(pattern, cleaned_text)

        for match in matches:
            result = ''.join(match)
            if is_valid_license_plate(result):
                return result

        return None

    def get_letter_mapping():
        """
        字母映射表（处理同音字和大小写问题）
        完整的字母映射，包括复合字母
        :return:
        """
        return {
            'a': 'A', 'b': 'B', 'c': 'C', 'd': 'D', 'e': 'E', 'f': 'F',
            'g': 'G', 'h': 'H', 'i': 'I', 'j': 'J', 'k': 'K', 'l': 'L',
            'm': 'M', 'n': 'N', 'o': 'O', 'p': 'P', 'q': 'Q', 'r': 'R',
            's': 'S', 't': 'T', 'u': 'U', 'v': 'V', 'w': 'W', 'x': 'X',
            'y': 'Y', 'z': 'Z',
            # 单字符同音字映射
            '啊': 'A', '阿': 'A',
            '比': 'B', '币': 'B', '必': 'B',
            '西': 'C', '昔': 'C', '习': 'C',
            '弟': 'D', '地': 'D', '第': 'D',
            '伊': 'I', '一': 'I', '衣': 'I', '医': 'I',
            '艾弗': 'F', '弗': 'F',
            '吉': 'G', '鸡': 'G',
            '艾尺': 'H', '尺': 'H',
            '艾': 'I', '爱': 'I',
            '杰': 'J', '节': 'J',
            '凯': 'K', '克': 'K',
            '艾尔': 'L', '尔': 'L', '了': 'L', '老': 'L',
            '艾马': 'M', '马': 'M',
            '艾娜': 'N', '娜': 'N', '内': 'N',
            '哦': 'O', '奥': 'O', '哦': 'O',
            '皮': 'P', '批': 'P',
            '吉乌': 'Q', '球': 'Q', '秋': 'Q',
            '艾儿': 'R', '儿': 'R',
            '艾丝': 'S', '丝': 'S',
            '提': 'T', '特': 'T',
            '优': 'U', '有': 'U',
            '维': 'V', '微': 'V',
            '达布柳': 'W', '达不留': 'W', '乌': 'W', '我': 'W',
            '艾克斯': 'X', '克斯': 'X', '克丝': 'X',
            '外': 'Y', '歪': 'Y',
            '贼德': 'Z', '兹': 'Z', '子': 'Z'
        }

    def is_valid_license_plate(text):
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

    xml = param.get("xml")
    query = param.get("query")
    confirm_text = param.get("confirm_text")

    # 匹配车牌号（格式：省份简称+字母+5位数字/字母组合）
    plate_pattern = r'<node[^>]*text="([京津冀晋蒙辽吉黑沪苏浙皖闽赣鲁豫鄂湘粤桂琼渝川黔云藏陕甘青宁新][A-Z][A-Z0-9]{5})"[^>]*bounds="([^"]+)"'
    plate_match = re.search(plate_pattern, xml)
    #匹配页面车牌
    plate_number = plate_match.group(1) if plate_match else ""
    # 匹配页面车牌按钮坐标
    plate_bounds = plate_match.group(2) if plate_match else ""

    if confirm_text:
        query_plate_number = extract_license_plate(confirm_text)
        if query_plate_number is None:
            #确认文本中不存在车牌信息
            if "换" in confirm_text:
                coordinates = bounds_to_coordinates(plate_bounds)
                if coordinates is None:
                    return {"code": 1}
                return {
                    "code": 0,
                    "clear_query": True,
                    "thought": f"用户想换一个车牌缴费，下一步应该点击车牌按钮进行更换车牌操作。",
                    "actions": [{
                        "action": "click",
                        "name": plate_number,
                        "coordinates": coordinates,
                    }],
                    "task_status": "车牌号校验"
                }
            elif "不需要" in confirm_text or "不用" in confirm_text or "结束" in confirm_text:
                return {
                    "code": 2,
                    "thought": f"用户说不需要交费了，下一步应该结束缴费流程。",
                    "hint": f"缴费流程已终止。",
                    "task_status": "关闭"
                }
            else:
                # query中无车牌信息,播报“当前车牌无缴费信息，请问是否需要更换其他车牌缴费”
                return {
                    "code": 0,
                    "thought": f"不知道用户是什么意思，需要再次询问用户要为哪个车牌缴费。",
                    "hint": f"当前车牌{plate_number}没有查询到停车信息，如果您要给其他车牌缴费请对我说“更换车牌”或直接说出您要查询的车牌号，如果不需要了请对我说“不需要了”。",
                    "task_status": "车牌号校验"
                }
        else:
            #确认文本中有车牌信息，判断是否和页面上的车牌信息一致，一致则输出提示“当前车牌无缴费信息”，不一致则点击车牌按钮
            if query_plate_number == plate_number:
                return {
                    "code": 0,
                    "thought": f"当前页面应该是捷停车缴费页面，用户要给车牌号为{query_plate_number}的车辆缴费，识别到图片中的该车牌没有停车信息，下一步应该询问用户是否需要更换其他车牌缴费。",
                    "hint": f"当前车牌{query_plate_number}没有查询到停车信息，请问是否需要更换其他车牌缴费？如果想要更换其他车牌缴费请对我说“更换车牌”或者直接说出车牌号，如果不需要了请对我说“不需要了”或者“结束”。",
                    "task_status": "车牌号校验"
                }
            else:
                coordinates = bounds_to_coordinates(plate_bounds)
                if coordinates is None:
                    return {"code": 1}
                #要让外部服务清除query
                return {
                    "code": 0,
                    "clear_query": True,
                    "thought": f"当前页面应该是捷停车缴费页面，用户要给车牌号为{query_plate_number}的车辆缴费，识别到图片中的车牌为{plate_number}，车牌号不一样，下一步应该点击车牌按钮进行更换车牌操作。",
                    "actions": [{
                        "action": "click",
                        "name": plate_number,
                        "coordinates": coordinates,
                    }],
                    "task_status": "车牌号校验"
                }
        pass
    else:
        query_plate_number = extract_license_plate(query)
        if query_plate_number is None:
            # query中无车牌信息,播报“当前车牌无缴费信息，请问是否需要更换其他车牌缴费”
            return {
                "code": 0,
                "thought": f"当前页面应该是捷停车缴费页面，车牌号为{plate_number}，没有查询到停车信息，但用户没有提到要给哪个车牌缴费，那应该先询问用户要为哪个车牌缴费。",
                "hint": f"当前车牌{plate_number}没有查询到停车信息，如果您要给其他车牌缴费请对我说“更换车牌”或直接说出您要查询的车牌号，如果不需要了请对我说“不需要了”。",
                "task_status": "车牌号校验"
            }
        else:
            #query中有车牌信息，判断是否和页面上的车牌信息一致，一致则输出提示“当前车牌无缴费信息”，不一致则点击车牌按钮
            if query_plate_number == plate_number:
                return {
                    "code": 0,
                    "thought": f"当前页面应该是捷停车缴费页面，用户要给车牌号为{query_plate_number}的车辆缴费，识别到图片中的该车牌没有停车信息，下一步应该询问用户是否需要更换其他车牌缴费。",
                    "hint": f"当前车牌{query_plate_number}没有查询到停车信息，请问是否需要更换其他车牌缴费？如果想要更换其他车牌缴费请对我说“更换车牌”或者直接说出车牌号，如果不需要了请对我说“不需要了”或者“结束”。",
                    "task_status": "车牌号校验"
                }
            else:
                coordinates = bounds_to_coordinates(plate_bounds)
                if coordinates is None:
                    return {"code": 1}
                return {
                    "code": 0,
                    "thought": f"当前页面应该是捷停车缴费页面，用户要给车牌号为{query_plate_number}的车辆缴费，识别到图片中的车牌为{plate_number}，车牌号不一样，下一步应该点击车牌按钮进行更换车牌操作。",
                    "actions": [{
                        "action": "click",
                        "name": plate_number,
                        "coordinates": coordinates,
                    }],
                    "task_status": "车牌号校验"
                }

if __name__ == '__main__':

    # 待处理的字符串
    text = '''
    <?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
<hierarchy rotation=\"1\">
    <node index=\"0\" text=\"\" resource-id=\"\" class=\"android.widget.FrameLayout\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[901,202][1658,1542]\">
        <node index=\"0\" text=\"\" resource-id=\"\" class=\"android.widget.FrameLayout\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"true\" enabled=\"true\" focusable=\"true\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[901,202][1658,1542]\">
            <node index=\"0\" text=\"\" resource-id=\"\" class=\"android.widget.RelativeLayout\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[901,202][1658,1542]\">
                <node index=\"0\" text=\"捷停车\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"true\" enabled=\"true\" focusable=\"true\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1222,247][1336,355]\" />
                <node index=\"1\" text=\"\" resource-id=\"\" class=\"android.widget.FrameLayout\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"true\" password=\"false\" selected=\"false\" bounds=\"[901,355][1658,1416]\">
                    <node index=\"0\" text=\"\" resource-id=\"\" class=\"android.widget.FrameLayout\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"true\" enabled=\"true\" focusable=\"true\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[901,355][1658,1416]\">
                        <node index=\"0\" text=\"\" resource-id=\"\" class=\"android.widget.FrameLayout\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[901,355][1658,1416]\">
                            <node index=\"0\" text=\"\" resource-id=\"\" class=\"android.webkit.WebView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"true\" focused=\"true\" scrollable=\"true\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[901,355][1661,1417]\">
                                <node index=\"0\" text=\"\" resource-id=\"\" class=\"android.view.View\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[901,355][1661,1417]\">
                                    <node index=\"0\" text=\"\" resource-id=\"\" class=\"android.view.View\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"true\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[901,355][1661,1417]\">
                                        <node index=\"0\" text=\"\" resource-id=\"payIndex\" class=\"android.view.View\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[901,373][1661,1417]\">
                                            <node index=\"0\" text=\"\" resource-id=\"\" class=\"android.view.View\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[914,373][1645,906]\">
                                                <node index=\"0\" text=\"\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1294,391][1645,906]\" />
                                                <node index=\"1\" text=\"\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1294,391][1645,906]\" />
                                                <node index=\"2\" text=\"\" resource-id=\"\" class=\"android.view.View\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[914,373][1645,769]\">
                                                    <node index=\"0\" text=\"\" resource-id=\"\" class=\"android.view.View\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[914,373][1645,769]\">
                                                        <node index=\"0\" text=\"皖AE27C3\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[946,393][1132,442]\" />
                                                        <node index=\"1\" text=\"未查询到停车信息\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1126,474][1434,537]\" />
                                                        <node index=\"2\" text=\"刷新订单\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[946,557][1614,658]\" />
                                                        <node index=\"3\" text=\"如车辆在场可咨询收费处\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1155,692][1405,728]\" />
                                                        <node index=\"5\" text=\"\" resource-id=\"\" class=\"android.view.View\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[964,760][1645,769]\" /></node>
                                                </node>
                                                <node index=\"3\" text=\"\" resource-id=\"\" class=\"android.view.View\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[916,782][1065,886]\">
                                                    <node index=\"0\" text=\"\" resource-id=\"\" class=\"android.view.View\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[916,782][1065,886]\">
                                                        <node index=\"0\" text=\"\" resource-id=\"\" class=\"android.widget.Image\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[957,782][1024,850]\" />
                                                        <node index=\"1\" text=\"月卡\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[916,845][1065,886]\" /></node>
                                                </node>
                                                <node index=\"4\" text=\"\" resource-id=\"\" class=\"android.view.View\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1063,782][1209,886]\">
                                                    <node index=\"0\" text=\"\" resource-id=\"\" class=\"android.view.View\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1063,782][1209,886]\">
                                                        <node index=\"0\" text=\"\" resource-id=\"\" class=\"android.widget.Image\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1103,782][1168,850]\" />
                                                        <node index=\"1\" text=\"电子发票\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1063,845][1209,886]\" /></node>
                                                </node>
                                                <node index=\"5\" text=\"\" resource-id=\"\" class=\"android.view.View\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1207,782][1353,886]\">
                                                    <node index=\"0\" text=\"\" resource-id=\"\" class=\"android.view.View\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1207,782][1353,886]\">
                                                        <node index=\"0\" text=\"\" resource-id=\"\" class=\"android.widget.Image\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1247,782][1312,850]\" />
                                                        <node index=\"1\" text=\"查订单\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1207,845][1353,886]\" /></node>
                                                </node>
                                                <node index=\"6\" text=\"\" resource-id=\"\" class=\"android.view.View\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1351,782][1499,886]\">
                                                    <node index=\"0\" text=\"\" resource-id=\"\" class=\"android.view.View\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1351,782][1499,886]\">
                                                        <node index=\"0\" text=\"\" resource-id=\"\" class=\"android.widget.Image\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1391,782][1459,850]\" />
                                                        <node index=\"1\" text=\"先出后付\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1351,845][1499,886]\" /></node>
                                                </node>
                                                <node index=\"7\" text=\"\" resource-id=\"\" class=\"android.view.View\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1495,782][1643,886]\">
                                                    <node index=\"0\" text=\"\" resource-id=\"\" class=\"android.view.View\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1495,782][1643,886]\">
                                                        <node index=\"0\" text=\"\" resource-id=\"\" class=\"android.widget.Image\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1537,782][1603,850]\" />
                                                        <node index=\"1\" text=\"找车位\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1495,845][1643,886]\" /></node>
                                                </node>
                                            </node>
                                            <node index=\"1\" text=\"最近消息\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[946,942][1040,976]\" />
                                            <node index=\"2\" text=\"暂无新消息\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1454,942][1569,976]\" />
                                            <node index=\"3\" text=\"\" resource-id=\"\" class=\"android.widget.Image\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1580,942][1614,976]\" />
                                            <node index=\"4\" text=\"\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[901,1012][1661,1417]\" />
                                            <node index=\"6\" text=\"\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[901,1012][1661,1417]\" />
                                            <node index=\"7\" text=\"我的停车币\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[946,1034][1243,1077]\" />
                                            <node index=\"8\" text=\"0\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[946,1075][1243,1158]\" />
                                            <node index=\"9\" text=\"可抵扣停车费\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[946,1162][1243,1196]\" />
                                            <node index=\"10\" text=\"每日签到\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1319,1036][1495,1077]\" />
                                            <node index=\"11\" text=\"+6停车币\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1319,1081][1495,1117]\" />
                                            <node index=\"12\" text=\"\" resource-id=\"\" class=\"android.view.View\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1492,1048][1614,1106]\">
                                                <node index=\"0\" text=\"签到\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1492,1048][1614,1106]\" /></node>
                                            <node index=\"13\" text=\"关注\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1319,1176][1495,1219]\" />
                                            <node index=\"14\" text=\"+100停车币\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1319,1223][1495,1257]\" />
                                            <node index=\"15\" text=\"\" resource-id=\"\" class=\"android.view.View\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1492,1187][1614,1246]\">
                                                <node index=\"0\" text=\"领取\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1492,1187][1614,1246]\" /></node>
                                            <node index=\"17\" text=\"\" resource-id=\"\" class=\"android.view.View\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[901,1293][1661,1363]\">
                                                <node index=\"0\" text=\"\" resource-id=\"\" class=\"android.widget.Image\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[928,1309][968,1347]\" />
                                                <node index=\"1\" text=\"车位优选\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[973,1304][1101,1354]\" />
                                                <node index=\"2\" text=\"｜停车优惠套餐\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1099,1306][1290,1349]\" />
                                                <node index=\"3\" text=\"更多优惠车场\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1459,1311][1632,1345]\" /></node>
                                        </node>
                                    </node>
                                </node>
                            </node>
                        </node>
                    </node>
                </node>
                <node index=\"3\" text=\"\" resource-id=\"\" class=\"android.widget.RelativeLayout\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"true\" checked=\"true\" clickable=\"true\" enabled=\"true\" focusable=\"true\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[901,1416][1052,1542]\">
                    <node index=\"0\" text=\"首页\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[940,1492][1012,1529]\" /></node>
                <node index=\"4\" text=\"\" resource-id=\"\" class=\"android.widget.RelativeLayout\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"true\" checked=\"false\" clickable=\"true\" enabled=\"true\" focusable=\"true\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1052,1416][1203,1542]\">
                    <node index=\"0\" text=\"车位优选\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1064,1492][1190,1529]\" /></node>
                <node index=\"5\" text=\"\" resource-id=\"\" class=\"android.widget.RelativeLayout\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"true\" checked=\"false\" clickable=\"true\" enabled=\"true\" focusable=\"true\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1203,1416][1354,1542]\">
                    <node index=\"0\" text=\"充电\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1242,1492][1314,1529]\" /></node>
                <node index=\"6\" text=\"\" resource-id=\"\" class=\"android.widget.RelativeLayout\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"true\" checked=\"false\" clickable=\"true\" enabled=\"true\" focusable=\"true\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1354,1416][1506,1542]\">
                    <node index=\"0\" text=\"优惠\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1394,1492][1466,1529]\" /></node>
                <node index=\"7\" text=\"\" resource-id=\"\" class=\"android.widget.RelativeLayout\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"true\" checked=\"false\" clickable=\"true\" enabled=\"true\" focusable=\"true\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1506,1416][1658,1542]\">
                    <node index=\"0\" text=\"我的\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1546,1492][1618,1529]\" /></node>
            </node>
            <node index=\"1\" text=\"\" resource-id=\"\" class=\"android.widget.ImageButton\" package=\"com.tencent.wmpf\" content-desc=\"更多\" checkable=\"false\" checked=\"false\" clickable=\"true\" enabled=\"true\" focusable=\"true\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1421,265][1529,337]\" />
            <node index=\"2\" text=\"\" resource-id=\"\" class=\"android.widget.ImageButton\" package=\"com.tencent.wmpf\" content-desc=\"关闭\" checkable=\"false\" checked=\"false\" clickable=\"true\" enabled=\"true\" focusable=\"true\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1530,265][1638,337]\" /></node>
        <node index=\"1\" text=\"\" resource-id=\"\" class=\"android.widget.FrameLayout\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1027,202][1531,247]\" /></node>
</hierarchy>
    '''

    param = {
        "xml": text,
        "query": "帮我给交一下停车费",
        "confirm_text": ""
    }
    res = rpa_func(param)
    print(json.dumps(res,     indent=4,ensure_ascii=False))

