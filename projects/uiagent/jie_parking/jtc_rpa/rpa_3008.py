
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

    plate_province_bounds_pattern = r'<node[^>]*text="([京津冀晋蒙辽吉黑沪苏浙皖闽赣鲁豫鄂湘粤桂琼渝川黔云藏陕甘青宁新])"[^>]*bounds="([^"]+)"'
    plate_province_bounds_match = re.search(plate_province_bounds_pattern, xml)
    province = plate_province_bounds_match.group(1) if plate_province_bounds_match else ""
    province_bounds = plate_province_bounds_match.group(2) if plate_province_bounds_match else ""
    if confirm_text is None or confirm_text == "":
        plate = extract_license_plate(query)
        if plate is None:
            return {
                "code": 0,
                "hint": "请问您的车牌是多少呢？",
                "thought": "当前是一个输入车牌的页面，但是用户好像没有说要输入什么车牌，应该提示用户说出车牌。",
                "task_status": "车牌号输入"
            }
        else:
            province_char = plate[0]  # 车牌省
            # 判断车牌省和界面省是否一致
            if province == province_char:
                # 一致  继续输入字母数字
                actions = []
                for item in plate[1:]:
                    # 点击字母数字
                    button_bounds_pattern = rf'<node[^>]*text="{item}"[^>]*bounds="([^"]+)"'
                    button_bounds_match = re.search(button_bounds_pattern, xml)
                    button_bounds = button_bounds_match.group(1) if button_bounds_match else ""
                    coordinates = bounds_to_coordinates(button_bounds)
                    actions.append({
                        "action": "click",
                        "name": item,
                        "coordinates": coordinates,
                    })
                button_bounds_pattern = rf'<node[^>]*text="完成"[^>]*bounds="([^"]+)"'
                button_bounds_match = re.search(button_bounds_pattern, xml)
                button_bounds = button_bounds_match.group(1) if button_bounds_match else ""
                coordinates = bounds_to_coordinates(button_bounds)
                actions.append({
                    "action": "click",
                    "name": "完成",
                    "coordinates": coordinates,
                })
                return {
                    "code": 0,
                    "thought": f"当前页面是车牌输入键盘，页面上已输入车牌省份“{province}”，下一步要输入车牌字母数字。",
                    "actions": actions,
                    "task_status": "车牌号输入"
                }
            else:
                # 不一致 要点击省份框
                coordinates = bounds_to_coordinates(province_bounds)
                if coordinates is None:
                    return {"code": 1}
                else:
                    return {
                        "code": 0,
                        "thought": f"当前页面是车牌输入键盘，页面上已输入车牌省份“{province}”，但用户要缴费的车牌是“{plate}”，所以下一步应该点击省份框进行更换省份操作。",
                        "actions": [
                            {
                                "action": "click",
                                "name": province,
                                "coordinates": coordinates,
                            }
                        ],
                        "task_status": "车牌号输入"
                    }
    else:
        plate = extract_license_plate(confirm_text)
        if plate is None:
            return {
                "code": 0,
                "hint": "请正确说出您的车牌。",
                "thought": "当前是一个输入车牌的页面，上一步已经提示用户说出要缴费的车牌，但是用户好像没有说，应该再次提示用户说出车牌。",
                "task_status": "车牌号输入"
            }
        else:
            province_char = plate[0] #车牌省
            #判断车牌省和界面省是否一致
            if province == province_char:
                #一致  继续输入字母数字
                actions = []
                for item in plate[1:]:
                    #点击字母数字
                    button_bounds_pattern = rf'<node[^>]*text="{item}"[^>]*bounds="([^"]+)"'
                    button_bounds_match = re.search(button_bounds_pattern, xml)
                    button_bounds = button_bounds_match.group(1) if button_bounds_match else ""
                    coordinates = bounds_to_coordinates(button_bounds)
                    actions.append({
                        "action": "click",
                        "name": item,
                        "coordinates": coordinates,
                    })
                button_bounds_pattern = rf'<node[^>]*text="完成"[^>]*bounds="([^"]+)"'
                button_bounds_match = re.search(button_bounds_pattern, xml)
                button_bounds = button_bounds_match.group(1) if button_bounds_match else ""
                coordinates = bounds_to_coordinates(button_bounds)
                actions.append({
                    "action": "click",
                    "name": "完成",
                    "coordinates": coordinates,
                })
                return {
                    "code": 0,
                    "thought": f"当前页面是车牌输入键盘，页面上已输入车牌省份“{province}”，下一步要输入车牌字母数字。",
                    "actions": actions,
                    "task_status": "车牌号输入"
                }
            else:
                #不一致 要点击省份框
                coordinates = bounds_to_coordinates(province_bounds)
                if coordinates is None:
                    return {"code": 1}
                else:
                    return {
                        "code": 0,
                        "thought": f"当前页面是车牌输入键盘，页面上已输入车牌省份“{province}”，但用户要缴费的车牌是“{plate}”，所以下一步应该点击省份框进行更换省份操作。",
                        "actions": [
                            {
                                "action": "click",
                                "name": province,
                                "coordinates": coordinates,
                            }
                        ],
                        "task_status": "车牌号输入"
                    }


if __name__ == '__main__':

    # 待处理的字符串
    text = '''
    <?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
<hierarchy rotation="1">
    <node index="0" text="" resource-id="" class="android.widget.FrameLayout" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[901,202][1658,1542]">
        <node index="0" text="" resource-id="" class="android.widget.FrameLayout" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="true" enabled="true" focusable="true" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[901,202][1658,1542]">
            <node index="0" text="" resource-id="" class="android.widget.RelativeLayout" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[901,202][1658,1542]">
                <node index="0" text="捷停车" resource-id="" class="android.widget.TextView" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="true" enabled="true" focusable="true" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[1222,247][1336,355]" />
                <node index="1" text="" resource-id="" class="android.widget.FrameLayout" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="true" password="false" selected="false" bounds="[901,355][1658,1416]">
                    <node index="0" text="" resource-id="" class="android.widget.FrameLayout" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="true" enabled="true" focusable="true" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[901,355][1658,1416]">
                        <node index="0" text="" resource-id="" class="android.widget.FrameLayout" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[901,355][1658,1416]">
                            <node index="0" text="" resource-id="" class="android.webkit.WebView" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="true" focused="true" scrollable="true" long-clickable="false" password="false" selected="false" bounds="[901,355][1661,1417]">
                                <node index="0" text="" resource-id="" class="android.view.View" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[901,355][1661,1417]">
                                    <node index="0" text="" resource-id="" class="android.view.View" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="true" long-clickable="false" password="false" selected="false" bounds="[901,355][1661,1417]">
                                        <node index="0" text="" resource-id="payIndex" class="android.view.View" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[901,373][1661,1417]">
                                            <node index="0" text="" resource-id="" class="android.view.View" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[914,373][1645,856]">
                                                <node index="0" text="" resource-id="" class="android.widget.TextView" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[1294,391][1645,856]" />
                                                <node index="1" text="" resource-id="" class="android.widget.TextView" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[1294,391][1645,856]" />
                                                <node index="2" text="" resource-id="" class="android.widget.Image" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[1198,420][1362,550]" />
                                                <node index="3" text="添加车辆缴费免排队、免找零" resource-id="" class="android.widget.TextView" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[1103,553][1456,595]" />
                                                <node index="4" text="" resource-id="" class="android.view.View" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[916,733][1065,834]">
                                                    <node index="0" text="" resource-id="" class="android.view.View" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[916,733][1065,834]">
                                                        <node index="0" text="" resource-id="" class="android.widget.Image" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[957,733][1024,798]" />
                                                        <node index="1" text="月卡" resource-id="" class="android.widget.TextView" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[916,796][1065,834]" /></node>
                                                </node>
                                                <node index="5" text="" resource-id="" class="android.view.View" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[1063,733][1209,834]">
                                                    <node index="0" text="" resource-id="" class="android.view.View" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[1063,733][1209,834]">
                                                        <node index="0" text="" resource-id="" class="android.widget.Image" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[1103,733][1168,798]" />
                                                        <node index="1" text="电子发票" resource-id="" class="android.widget.TextView" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[1063,796][1209,834]" /></node>
                                                </node>
                                                <node index="6" text="" resource-id="" class="android.view.View" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[1207,733][1353,834]">
                                                    <node index="0" text="" resource-id="" class="android.view.View" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[1207,733][1353,834]">
                                                        <node index="0" text="" resource-id="" class="android.widget.Image" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[1247,733][1312,798]" />
                                                        <node index="1" text="查订单" resource-id="" class="android.widget.TextView" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[1207,796][1353,834]" /></node>
                                                </node>
                                                <node index="7" text="" resource-id="" class="android.view.View" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[1351,733][1499,834]">
                                                    <node index="0" text="" resource-id="" class="android.view.View" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[1351,733][1499,834]">
                                                        <node index="0" text="" resource-id="" class="android.widget.Image" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[1391,733][1459,798]" />
                                                        <node index="1" text="先出后付" resource-id="" class="android.widget.TextView" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[1351,796][1499,834]" /></node>
                                                </node>
                                                <node index="8" text="" resource-id="" class="android.view.View" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[1495,733][1643,834]">
                                                    <node index="0" text="" resource-id="" class="android.view.View" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[1495,733][1643,834]">
                                                        <node index="0" text="" resource-id="" class="android.widget.Image" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[1537,733][1603,798]" />
                                                        <node index="1" text="找车位" resource-id="" class="android.widget.TextView" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[1495,796][1643,834]" /></node>
                                                </node>
                                            </node>
                                            <node index="1" text="最近消息" resource-id="" class="android.widget.TextView" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[946,892][1040,926]" />
                                            <node index="2" text="暂无新消息" resource-id="" class="android.widget.TextView" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[1454,892][1569,926]" />
                                            <node index="3" text="" resource-id="" class="android.widget.Image" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[1580,892][1614,926]" />
                                            <node index="4" text="" resource-id="" class="android.widget.TextView" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[901,962][1661,1417]" />
                                            <node index="6" text="" resource-id="" class="android.widget.TextView" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[901,962][1661,1417]" />
                                            <node index="7" text="我的停车币" resource-id="" class="android.widget.TextView" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[946,985][1243,1025]" />
                                            <node index="8" text="0" resource-id="" class="android.widget.TextView" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[946,1023][1243,1106]" />
                                            <node index="9" text="可抵扣停车费" resource-id="" class="android.widget.TextView" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[946,1111][1243,1147]" />
                                            <node index="10" text="每日签到" resource-id="" class="android.widget.TextView" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[1319,985][1495,1027]" />
                                            <node index="11" text="+6停车币" resource-id="" class="android.widget.TextView" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[1319,1030][1495,1066]" />
                                            <node index="12" text="" resource-id="" class="android.view.View" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[1492,996][1614,1054]">
                                                <node index="0" text="签到" resource-id="" class="android.widget.TextView" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[1492,996][1614,1054]" /></node>
                                            <node index="13" text="关注" resource-id="" class="android.widget.TextView" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[1319,1126][1495,1167]" />
                                            <node index="14" text="+100停车币" resource-id="" class="android.widget.TextView" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[1319,1171][1495,1207]" />
                                            <node index="15" text="" resource-id="" class="android.view.View" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[1492,1138][1614,1196]">
                                                <node index="0" text="领取" resource-id="" class="android.widget.TextView" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[1492,1138][1614,1196]" /></node>
                                            <node index="17" text="" resource-id="" class="android.view.View" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[901,1243][1661,1311]">
                                                <node index="0" text="" resource-id="" class="android.widget.Image" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[928,1257][968,1297]" />
                                                <node index="1" text="车位优选" resource-id="" class="android.widget.TextView" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[973,1252][1101,1302]" />
                                                <node index="2" text="｜停车优惠套餐" resource-id="" class="android.widget.TextView" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[1099,1255][1290,1297]" />
                                                <node index="3" text="更多优惠车场" resource-id="" class="android.widget.TextView" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[1459,1259][1632,1295]" /></node>
                                            <node index="18" text="" resource-id="" class="android.widget.Image" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[1204,1374][1357,1417]" /></node>
                                        <node index="2" text="" resource-id="" class="android.view.View" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[901,355][1661,1417]">
                                            <node index="0" text="" resource-id="" class="android.view.View" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[901,460][1661,1417]">
                                                <node index="0" text="请输入车牌授权定位，提高查费准确性" resource-id="" class="android.widget.TextView" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[919,496][1452,550]" />
                                                <node index="1" text="" resource-id="" class="android.view.View" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[1603,496][1643,550]">
                                                    <node index="0" text="" resource-id="" class="android.widget.Image" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[1603,499][1643,539]" /></node>
                                                <node index="2" text="普通车牌" resource-id="" class="android.widget.TextView" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[919,580][1047,627]" />
                                                <node index="3" text="特殊车牌（港澳本土牌）" resource-id="" class="android.widget.TextView" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[1090,582][1360,625]" />
                                                <node index="4" text="" resource-id="" class="android.view.View" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[919,670][1000,778]">
                                                    <node index="0" text="沪" resource-id="" class="android.widget.TextView" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[934,688][982,760]" /></node>
                                                <node index="5" text="" resource-id="" class="android.view.View" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[1006,670][1087,778]">
                                                    <node index="0" text="" resource-id="" class="android.widget.TextView" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[1024,688][1072,760]" /></node>
                                                <node index="6" text="" resource-id="" class="android.view.View" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[1117,670][1200,778]">
                                                    <node index="0" text="" resource-id="" class="android.widget.TextView" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[1135,688][1182,760]" /></node>
                                                <node index="7" text="" resource-id="" class="android.view.View" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[1207,670][1288,778]">
                                                    <node index="0" text="" resource-id="" class="android.widget.TextView" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[1222,688][1270,760]" /></node>
                                                <node index="8" text="" resource-id="" class="android.view.View" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[1294,670][1378,778]">
                                                    <node index="0" text="" resource-id="" class="android.widget.TextView" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[1312,688][1360,760]" /></node>
                                                <node index="9" text="" resource-id="" class="android.view.View" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[1384,670][1465,778]">
                                                    <node index="0" text="" resource-id="" class="android.widget.TextView" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[1400,688][1450,760]" /></node>
                                                <node index="10" text="" resource-id="" class="android.view.View" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[1472,670][1553,778]">
                                                    <node index="0" text="" resource-id="" class="android.widget.TextView" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[1488,688][1537,760]" /></node>
                                                <node index="11" text="" resource-id="" class="android.view.View" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[1560,670][1643,778]">
                                                    <node index="0" text="新能源" resource-id="" class="android.widget.TextView" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[1562,708][1643,737]" /></node>
                                                <node index="12" text="中大型车辆（黄牌车）" resource-id="" class="android.widget.TextView" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[901,800][1661,843]" />
                                                <node index="13" text="查询缴费" resource-id="" class="android.widget.TextView" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[930,859][1630,960]" />
                                                <node index="14" text="" resource-id="" class="android.view.View" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[901,910][1661,1417]">
                                                    <node index="0" text="" resource-id="" class="android.view.View" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[901,910][1661,985]">
                                                        <node index="0" text="完成" resource-id="" class="android.widget.TextView" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[1558,913][1632,985]" /></node>
                                                    <node index="1" text="1" resource-id="" class="android.widget.TextView" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[905,1003][973,1090]" />
                                                    <node index="2" text="2" resource-id="" class="android.widget.TextView" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[982,1003][1047,1090]" />
                                                    <node index="3" text="3" resource-id="" class="android.widget.TextView" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[1056,1003][1123,1090]" />
                                                    <node index="4" text="4" resource-id="" class="android.widget.TextView" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[1132,1003][1198,1090]" />
                                                    <node index="5" text="5" resource-id="" class="android.widget.TextView" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[1207,1003][1272,1090]" />
                                                    <node index="6" text="6" resource-id="" class="android.widget.TextView" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[1283,1003][1348,1090]" />
                                                    <node index="7" text="7" resource-id="" class="android.widget.TextView" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[1357,1003][1423,1090]" />
                                                    <node index="8" text="8" resource-id="" class="android.widget.TextView" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[1434,1003][1499,1090]" />
                                                    <node index="9" text="9" resource-id="" class="android.widget.TextView" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[1508,1003][1576,1090]" />
                                                    <node index="10" text="0" resource-id="" class="android.widget.TextView" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[1585,1003][1650,1090]" />
                                                    <node index="11" text="Q" resource-id="" class="android.widget.TextView" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[905,1097][973,1183]" />
                                                    <node index="12" text="W" resource-id="" class="android.widget.TextView" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[982,1097][1047,1183]" />
                                                    <node index="13" text="E" resource-id="" class="android.widget.TextView" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[1056,1097][1123,1183]" />
                                                    <node index="14" text="R" resource-id="" class="android.widget.TextView" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[1132,1097][1198,1183]" />
                                                    <node index="15" text="T" resource-id="" class="android.widget.TextView" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[1207,1097][1272,1183]" />
                                                    <node index="16" text="Y" resource-id="" class="android.widget.TextView" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[1283,1097][1348,1183]" />
                                                    <node index="17" text="U" resource-id="" class="android.widget.TextView" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[1357,1097][1423,1183]" />
                                                    <node index="18" text="O" resource-id="" class="android.widget.TextView" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[1434,1097][1499,1183]" />
                                                    <node index="19" text="P" resource-id="" class="android.widget.TextView" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[1508,1097][1576,1183]" />
                                                    <node index="20" text="港" resource-id="" class="android.widget.TextView" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[1585,1097][1650,1183]" />
                                                    <node index="21" text="A" resource-id="" class="android.widget.TextView" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[905,1192][973,1279]" />
                                                    <node index="22" text="S" resource-id="" class="android.widget.TextView" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[982,1192][1047,1279]" />
                                                    <node index="23" text="D" resource-id="" class="android.widget.TextView" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[1056,1192][1123,1279]" />
                                                    <node index="24" text="F" resource-id="" class="android.widget.TextView" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[1132,1192][1198,1279]" />
                                                    <node index="25" text="G" resource-id="" class="android.widget.TextView" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[1207,1192][1272,1279]" />
                                                    <node index="26" text="H" resource-id="" class="android.widget.TextView" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[1283,1192][1348,1279]" />
                                                    <node index="27" text="J" resource-id="" class="android.widget.TextView" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[1357,1192][1423,1279]" />
                                                    <node index="28" text="K" resource-id="" class="android.widget.TextView" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[1434,1192][1499,1279]" />
                                                    <node index="29" text="L" resource-id="" class="android.widget.TextView" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[1508,1192][1576,1279]" />
                                                    <node index="30" text="澳" resource-id="" class="android.widget.TextView" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[1585,1192][1650,1279]" />
                                                    <node index="31" text="Z" resource-id="" class="android.widget.TextView" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[905,1286][973,1372]" />
                                                    <node index="32" text="X" resource-id="" class="android.widget.TextView" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[982,1286][1047,1372]" />
                                                    <node index="33" text="C" resource-id="" class="android.widget.TextView" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[1056,1286][1123,1372]" />
                                                    <node index="34" text="V" resource-id="" class="android.widget.TextView" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[1132,1286][1198,1372]" />
                                                    <node index="35" text="B" resource-id="" class="android.widget.TextView" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[1207,1286][1272,1372]" />
                                                    <node index="36" text="N" resource-id="" class="android.widget.TextView" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[1283,1286][1348,1372]" />
                                                    <node index="37" text="M" resource-id="" class="android.widget.TextView" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[1357,1286][1423,1372]" />
                                                    <node index="38" text="学" resource-id="" class="android.widget.TextView" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[1434,1286][1499,1372]" />
                                                    <node index="39" text="领" resource-id="" class="android.widget.TextView" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[1508,1286][1576,1372]" /></node>
                                            </node>
                                        </node>
                                    </node>
                                </node>
                            </node>
                        </node>
                    </node>
                </node>
                <node index="3" text="" resource-id="" class="android.widget.RelativeLayout" package="com.tencent.wmpf" content-desc="" checkable="true" checked="true" clickable="true" enabled="true" focusable="true" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[901,1416][1052,1542]">
                    <node index="0" text="首页" resource-id="" class="android.widget.TextView" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[940,1492][1012,1529]" /></node>
                <node index="4" text="" resource-id="" class="android.widget.RelativeLayout" package="com.tencent.wmpf" content-desc="" checkable="true" checked="false" clickable="true" enabled="true" focusable="true" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[1052,1416][1203,1542]">
                    <node index="0" text="车位优选" resource-id="" class="android.widget.TextView" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[1064,1492][1190,1529]" /></node>
                <node index="5" text="" resource-id="" class="android.widget.RelativeLayout" package="com.tencent.wmpf" content-desc="" checkable="true" checked="false" clickable="true" enabled="true" focusable="true" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[1203,1416][1354,1542]">
                    <node index="0" text="充电" resource-id="" class="android.widget.TextView" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[1242,1492][1314,1529]" /></node>
                <node index="6" text="" resource-id="" class="android.widget.RelativeLayout" package="com.tencent.wmpf" content-desc="" checkable="true" checked="false" clickable="true" enabled="true" focusable="true" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[1354,1416][1506,1542]">
                    <node index="0" text="优惠" resource-id="" class="android.widget.TextView" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[1394,1492][1466,1529]" /></node>
                <node index="7" text="" resource-id="" class="android.widget.RelativeLayout" package="com.tencent.wmpf" content-desc="" checkable="true" checked="false" clickable="true" enabled="true" focusable="true" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[1506,1416][1658,1542]">
                    <node index="0" text="我的" resource-id="" class="android.widget.TextView" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[1546,1492][1618,1529]" /></node>
            </node>
            <node index="1" text="" resource-id="" class="android.widget.ImageButton" package="com.tencent.wmpf" content-desc="更多" checkable="false" checked="false" clickable="true" enabled="true" focusable="true" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[1421,265][1529,337]" />
            <node index="2" text="" resource-id="" class="android.widget.ImageButton" package="com.tencent.wmpf" content-desc="关闭" checkable="false" checked="false" clickable="true" enabled="true" focusable="true" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[1530,265][1638,337]" /></node>
        <node index="1" text="" resource-id="" class="android.widget.FrameLayout" package="com.tencent.wmpf" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[1027,202][1531,247]" /></node>
</hierarchy>
    '''

    param = {
        "xml": text,
        "query": "帮我交一下停车费",
        "confirm_text": "这AE27C3"
    }
    res = rpa_func(param)
    print(json.dumps(res,     indent=4,ensure_ascii=False))

