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
    plate_pattern = r'text="([京津冀晋蒙辽吉黑沪苏浙皖闽赣鲁豫鄂湘粤桂琼渝川黔云藏陕甘青宁新][A-Z][A-Z0-9]{5})"'
    plate_match = re.search(plate_pattern, xml)
    plate_number = plate_match.group(1) if plate_match else ""

    query_plate_pattern = r'[京津沪渝冀豫云辽黑湘皖鲁新苏浙赣鄂桂甘晋蒙陕吉闽贵川青藏琼宁港澳粤][A-HJ-NP-Z][A-HJ-NP-Z0-9]{5,6}'

    #匹配车牌按钮坐标
    plate_bounds_pattern = r'<node[^>]*text="([京津冀晋蒙辽吉黑沪苏浙皖闽赣鲁豫鄂湘粤桂琼渝川黔云藏陕甘青宁新][A-Z][A-Z0-9]{5})"[^>]*bounds="([^"]+)"'
    plate_bounds_match = re.search(plate_bounds_pattern, xml)
    plate_bounds = plate_bounds_match.group(2) if plate_bounds_match else ""


    # 匹配停车时长（格式：已停：X天X小时X分钟）
    duration_pattern = r'text="已停：(\d+天\d+小时\d+分钟)"'
    duration_match = re.search(duration_pattern, xml)
    parking_duration = duration_match.group(1) if duration_match else ""

    # 匹配订单金额（格式：数字+两位小数，前面可能有￥符号）
    amount_pattern = r'text="(\d+\.\d{2})"'
    amount_match = re.search(amount_pattern, xml)
    order_amount = f"{amount_match.group(1)}元" if amount_match else ""

    # 正则表达式模式：匹配text为"查看费用明细"的node节点中的bounds值
    button_bounds_pattern = r'<node[^>]*text="查看费用明细"[^>]*bounds="([^"]+)"'
    button_bounds_match = re.search(button_bounds_pattern, xml)
    button_bounds = button_bounds_match.group(1) if button_bounds_match else ""

    if confirm_text:
        confirm_plate_number = extract_license_plate(confirm_text)
        if confirm_plate_number is not None and confirm_plate_number != plate_number:
            #确认文本中包含车牌且与识别到的车牌不一致，则要点击车牌号，查询其他车牌
            coordinates = bounds_to_coordinates(plate_bounds)
            if coordinates is None:
                return {"code": 1}
            return {
                "code": 0,
                "clear_query": True,
                "thought": f"当前页面应该是捷停车缴费页面，用户要给车牌号为{confirm_plate_number}的车辆缴费，识别到图片中的车牌为{plate_number}，车牌号不一样，下一步应该点击车牌按钮进行更换车牌操作。",
                "actions": [{
                    "action": "click",
                    "name": plate_number,
                    "coordinates": coordinates,
                }],
                "task_status": "车牌号校验"
            }
        else:
            if "确认" in confirm_text or "确定" in confirm_text:
                coordinates = bounds_to_coordinates(button_bounds)
                if coordinates is None:
                    return {"code": 1}
                coordinates = {
                    "x1": coordinates["x1"] + 5,
                    "y1": coordinates["y1"] + 5,
                    "x2": coordinates["x2"] - 5,
                    "y2": coordinates["y2"] - 5
                }
                return {
                    "code": 0,
                    "thought": f"用户已确认当前订单，下一步应该点击“查看费用明细”按钮。",
                    "actions": [{
                        "action": "click",
                        "name": "查看费用",
                        "coordinates": coordinates,
                    }],
                    "task_status": "订单查询"
                }
            elif "不" in confirm_text or "其他" in confirm_text or "换" in confirm_text:
                coordinates = bounds_to_coordinates(plate_bounds)
                if coordinates is None:
                    return {"code": 1}
                return {
                    "code": 0,
                    "clear_query": True,
                    "thought": f"当前页面应该是捷停车缴费页面，用户应该是想更换其他车牌进行缴费，下一步应该点击车牌按钮进行更换车牌操作。",
                    "actions": [{
                        "action": "click",
                        "name": plate_number,
                        "coordinates": coordinates,
                    }],
                    "task_status": "车牌号校验"
                }
            elif "取消" in confirm_text or "结束" in confirm_text:
                return {
                    "code": 2,
                    "hint": f"好的，缴费流程已终止。",
                    "thought": f"用户取消了缴费流程，下一步应该结束流程。",
                    "task_status": "关闭"
                }
            else:
                return {
                    "code": 0,
                    "hint": f"我不明白您的意思，请说“确认”、“取消”、或者“更换车牌缴费”。",
                    "thought": f"当前图片应该是捷停车缴费页面，上一步已经提示用户确认订单，但用户好像没有确认，所以下一步应该返回提示用户告诉我需要确认订单还是取消订单，或者是更换车牌缴费。",
                    "task_status": "车牌号校验"
                }

    else:
        #首次进入rpa
        query_plate_number = extract_license_plate(query)
        #如果用户query中包含车牌，且与识别到的车牌不一致，则要点击车牌号，查询其他车牌
        if query_plate_number is not None and query_plate_number != plate_number:
            #返回点击车牌号的按钮
            coordinates = bounds_to_coordinates(plate_bounds)
            if coordinates is None:
                return {"code": 1}
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
        else:
            #返回当前账单信息，以及询问用户是否确认
            return {
                "code": 0,
                "hint": f"当前车牌号为：{plate_number}，停车时长：{parking_duration}，订单金额：{order_amount}，是否确认订单？",
                "thought": f"当前图片应该是捷停车缴费页面，识别到车牌为{plate_number}，停车时长为{parking_duration}，订单金额{order_amount}，下一步应该询问用户是否确认订单，确认了才能进行缴费。",
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
                                            <node index=\"0\" text=\"\" resource-id=\"\" class=\"android.view.View\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[914,373][1645,832]\">
                                                <node index=\"0\" text=\"\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1294,391][1645,832]\" />
                                                <node index=\"1\" text=\"\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1294,391][1645,832]\" />
                                                <node index=\"2\" text=\"\" resource-id=\"\" class=\"android.view.View\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[914,373][1645,694]\">
                                                    <node index=\"0\" text=\"\" resource-id=\"\" class=\"android.view.View\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[914,373][1645,694]\">
                                                        <node index=\"0\" text=\"鄂A12456\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[946,393][1128,442]\" />
                                                        <node index=\"1\" text=\"已停：18天4小时12分钟\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1369,406][1614,431]\" />
                                                        <node index=\"2\" text=\"\" resource-id=\"\" class=\"android.view.View\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1182,467][1378,539]\">
                                                            <node index=\"0\" text=\"\" resource-id=\"\" class=\"android.view.View\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1182,467][1378,532]\">
                                                                <node index=\"0\" text=\"￥\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1148,469][1189,535]\" />
                                                                <node index=\"1\" text=\"565.00\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1182,454][1378,546]\" /></node>
                                                        </node>
                                                        <node index=\"3\" text=\"查看费用明细\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[946,535][1614,670]\" />
                                                        <node index=\"5\" text=\"\" resource-id=\"\" class=\"android.view.View\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[964,685][1645,694]\" /></node>
                                                </node>
                                                <node index=\"3\" text=\"\" resource-id=\"\" class=\"android.view.View\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[916,708][1065,809]\">
                                                    <node index=\"0\" text=\"\" resource-id=\"\" class=\"android.view.View\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[916,708][1065,809]\">
                                                        <node index=\"0\" text=\"\" resource-id=\"\" class=\"android.widget.Image\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[957,708][1024,773]\" />
                                                        <node index=\"1\" text=\"月卡\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[916,771][1065,809]\" /></node>
                                                </node>
                                                <node index=\"4\" text=\"\" resource-id=\"\" class=\"android.view.View\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1063,708][1209,809]\">
                                                    <node index=\"0\" text=\"\" resource-id=\"\" class=\"android.view.View\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1063,708][1209,809]\">
                                                        <node index=\"0\" text=\"\" resource-id=\"\" class=\"android.widget.Image\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1103,708][1168,773]\" />
                                                        <node index=\"1\" text=\"电子发票\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1063,771][1209,809]\" /></node>
                                                </node>
                                                <node index=\"5\" text=\"\" resource-id=\"\" class=\"android.view.View\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1207,708][1353,809]\">
                                                    <node index=\"0\" text=\"\" resource-id=\"\" class=\"android.view.View\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1207,708][1353,809]\">
                                                        <node index=\"0\" text=\"\" resource-id=\"\" class=\"android.widget.Image\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1247,708][1312,773]\" />
                                                        <node index=\"1\" text=\"查订单\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1207,771][1353,809]\" /></node>
                                                </node>
                                                <node index=\"6\" text=\"\" resource-id=\"\" class=\"android.view.View\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1351,708][1499,809]\">
                                                    <node index=\"0\" text=\"\" resource-id=\"\" class=\"android.view.View\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1351,708][1499,809]\">
                                                        <node index=\"0\" text=\"\" resource-id=\"\" class=\"android.widget.Image\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1391,708][1459,773]\" />
                                                        <node index=\"1\" text=\"先出后付\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1351,771][1499,809]\" /></node>
                                                </node>
                                                <node index=\"7\" text=\"\" resource-id=\"\" class=\"android.view.View\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1495,708][1643,809]\">
                                                    <node index=\"0\" text=\"\" resource-id=\"\" class=\"android.view.View\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1495,708][1643,809]\">
                                                        <node index=\"0\" text=\"\" resource-id=\"\" class=\"android.widget.Image\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1537,708][1603,773]\" />
                                                        <node index=\"1\" text=\"找车位\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1495,771][1643,809]\" /></node>
                                                </node>
                                            </node>
                                            <node index=\"1\" text=\"最近消息\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[946,868][1040,904]\" />
                                            <node index=\"2\" text=\"暂无新消息\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1454,868][1569,904]\" />
                                            <node index=\"3\" text=\"\" resource-id=\"\" class=\"android.widget.Image\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1580,868][1614,904]\" />
                                            <node index=\"4\" text=\"\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[901,940][1661,1417]\" />
                                            <node index=\"6\" text=\"\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[901,940][1661,1417]\" />
                                            <node index=\"7\" text=\"我的停车币\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[946,960][1243,1003]\" />
                                            <node index=\"8\" text=\"0\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[946,1000][1243,1084]\" />
                                            <node index=\"9\" text=\"可抵扣停车费\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[946,1088][1243,1122]\" />
                                            <node index=\"10\" text=\"每日签到\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1319,962][1495,1003]\" />
                                            <node index=\"11\" text=\"+6停车币\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1319,1007][1495,1043]\" />
                                            <node index=\"12\" text=\"\" resource-id=\"\" class=\"android.view.View\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1492,973][1614,1032]\">
                                                <node index=\"0\" text=\"签到\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1492,973][1614,1032]\" /></node>
                                            <node index=\"13\" text=\"关注\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1319,1102][1495,1144]\" />
                                            <node index=\"14\" text=\"+100停车币\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1319,1147][1495,1183]\" />
                                            <node index=\"15\" text=\"\" resource-id=\"\" class=\"android.view.View\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1492,1113][1614,1174]\">
                                                <node index=\"0\" text=\"领取\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1492,1113][1614,1174]\" /></node>
                                            <node index=\"17\" text=\"\" resource-id=\"\" class=\"android.view.View\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[901,1219][1661,1288]\">
                                                <node index=\"0\" text=\"\" resource-id=\"\" class=\"android.widget.Image\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[928,1234][968,1273]\" />
                                                <node index=\"1\" text=\"车位优选\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[973,1228][1101,1277]\" />
                                                <node index=\"2\" text=\"｜停车优惠套餐\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1099,1232][1290,1275]\" />
                                                <node index=\"3\" text=\"更多优惠车场\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1459,1237][1632,1270]\" /></node>
                                            <node index=\"18\" text=\"\" resource-id=\"\" class=\"android.widget.Image\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1204,1349][1357,1417]\" /></node>
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

