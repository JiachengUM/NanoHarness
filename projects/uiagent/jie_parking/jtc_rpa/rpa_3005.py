
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

    xml = param.get("xml")
    query = param.get("query")
    confirm_text = param.get("confirm_text")

    button_bounds_pattern = r'<node[^>]*text="添加车辆缴费免排队、免找零"[^>]*bounds="([^"]+)"'
    button_bounds_match = re.search(button_bounds_pattern, xml)
    button_bounds = button_bounds_match.group(1) if button_bounds_match else ""
    coordinates = bounds_to_coordinates(button_bounds)
    if coordinates is None:
        return {"code": 1}
    else:
        x = int((coordinates["x1"] + coordinates["x2"])/2)
        y = int((coordinates["y1"] + coordinates["y2"])/2) + 75
        return {
            "code": 0,
            "thought": f"当前页面应该是捷停车首页，要缴停车费，识别到页面有一个“+输车牌缴费”按钮，下一步应该点击这个按钮去添加车牌。",
            "actions": [{
                "action": "click",
                "name": "+输车牌缴费",
                "coordinates": {
                    "x1": x - 2,
                    "y1": y - 2,
                    "x2": x + 2,
                    "y2": y + 2
                },
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
                                    <node index=\"0\" text=\"\" resource-id=\"\" class=\"android.view.View\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[901,355][1661,1417]\">
                                        <node index=\"0\" text=\"\" resource-id=\"payIndex\" class=\"android.view.View\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[901,373][1661,1203]\">
                                            <node index=\"0\" text=\"\" resource-id=\"\" class=\"android.view.View\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[914,373][1645,717]\">
                                                <node index=\"0\" text=\"\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1294,391][1645,717]\" />
                                                <node index=\"1\" text=\"\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1294,391][1645,717]\" />
                                                <node index=\"2\" text=\"\" resource-id=\"\" class=\"android.widget.Image\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1198,420][1362,550]\" />
                                                <node index=\"3\" text=\"添加车辆缴费免排队、免找零\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1103,553][1456,595]\" /></node>
                                            <node index=\"1\" text=\"最近消息\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[946,751][1040,787]\" />
                                            <node index=\"2\" text=\"暂无新消息\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1454,751][1569,787]\" />
                                            <node index=\"3\" text=\"\" resource-id=\"\" class=\"android.widget.Image\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1580,753][1614,787]\" />
                                            <node index=\"4\" text=\"\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[901,823][1661,1203]\" /></node>
                                        <node index=\"1\" text=\"\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[901,1201][1661,1417]\" />
                                        <node index=\"2\" text=\"\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[901,1201][1661,1417]\" /></node>
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
        "query": "帮我交一下停车费",
    }
    res = rpa_func(param)
    print(json.dumps(res,     indent=4,ensure_ascii=False))

