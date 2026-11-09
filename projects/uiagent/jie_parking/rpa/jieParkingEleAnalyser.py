# 捷停车页面专用分析
import re


def find_plate_input_loc(xml_content, index=1) -> dict:
    """
    在 XML 布局中查找“特殊车牌（港澳本土牌）”下方的第一个车牌输入框（TextView）。
    Args:
        xml_content (str): XML 布局字符串
        index: 第几个车牌输入框
    return {"center": (x, y)} or {}
    """
    import xml.etree.ElementTree as ET
    root = ET.fromstring(xml_content)

    # 查找文本为“特殊车牌（港澳本土牌）”的 TextView 节点
    target_text = "特殊车牌（港澳本土牌）"
    special_plate_node = None
    for node in root.iter():
        if node.get("text") == target_text and node.get("class") == "android.widget.TextView":
            special_plate_node = node
            break

    if special_plate_node is None:
        return {}

    # 获取父节点
    parent = special_plate_node.find('..')  # 注意：ET 不直接支持 '..'，需换方式

    # 更可靠的方式：遍历所有节点，找到 parent
    def find_parent(root, child):
        for elem in root.iter():
            for subelem in elem:
                if subelem is child:
                    return elem
        return {}

    parent = find_parent(root, special_plate_node)
    if parent is None:
        return {}

    # 获取该节点在父节点中的索引
    siblings = list(parent)
    try:
        idx = siblings.index(special_plate_node)
    except ValueError:
        return {}

    # 从下一个节点开始查找第一个包含 TextView 的 View（模拟输入框）
    input_box = []
    for i in range(idx + 1, len(siblings)):
        sibling = siblings[i]
        # 跳过非 View 容器（我们期望的是 android.view.View 包含 TextView）
        if sibling.get("class") == "android.view.View":
            # 查找其内部的 TextView
            inner_textview = sibling.find(".//*[@class='android.widget.TextView']")
            if inner_textview is not None:
                # 返回该 TextView 的属性
                input_box.append(inner_textview.get("bounds"))
                # return inner_textview.get("bounds")
        # 也考虑直接是 TextView 的情况（虽然当前结构不是）
        elif sibling.get("class") == "android.widget.TextView":
            input_box.append(sibling.get("bounds"))
            # return sibling.get("bounds")
    
    
    if len(input_box) >= index:
        bounds = input_box[index-1]
        match = re.search(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', bounds)
        if not match:
            return {}

        x1, y1, x2, y2 = map(int, match.groups())

        # 计算中心点
        cx = (x1 + x2) // 2
        cy = (y1 + y2) // 2
        return {"center": (cx, cy)}
    return {}