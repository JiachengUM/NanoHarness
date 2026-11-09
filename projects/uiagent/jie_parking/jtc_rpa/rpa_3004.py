
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

    button_bounds_pattern = r'<node[^>]*text="二维码支付"[^>]*bounds="([^"]+)"'
    button_bounds_match = re.search(button_bounds_pattern, xml)
    button_bounds = button_bounds_match.group(1) if button_bounds_match else ""
    coordinates = bounds_to_coordinates(button_bounds)
    if coordinates is None:
        return {"code": 1}
    else:
        return {
            "code": 0,
            "thought": f"页面上有发送到手机微信支付和二维码支付，二维码支付更便捷，所以下一步应该点击“二维码支付”按钮。",
            "actions": [{
                "action": "click",
                "name": "二维码支付",
                "coordinates": coordinates,
            }],
            "task_status": "任务完成"
        }

if __name__ == '__main__':

    # 待处理的字符串
    text = '''
    <?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
<hierarchy rotation=\"1\">
    <node index=\"0\" text=\"\" resource-id=\"\" class=\"android.widget.FrameLayout\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[901,202][1658,1542]\">
        <node index=\"0\" text=\"\" resource-id=\"\" class=\"android.widget.FrameLayout\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"true\" enabled=\"true\" focusable=\"true\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[901,202][1658,1542]\">
            <node index=\"0\" text=\"\" resource-id=\"\" class=\"android.widget.RelativeLayout\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"true\" enabled=\"true\" focusable=\"true\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[901,202][1658,1542]\">
                <node index=\"0\" text=\"\" resource-id=\"\" class=\"android.widget.FrameLayout\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"true\" focused=\"true\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[938,483][1621,1261]\">
                    <node index=\"0\" text=\"订单支付\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1207,834][1351,883]\" />
                    <node index=\"1\" text=\"发送到手机微信支付\" resource-id=\"\" class=\"android.widget.Button\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"true\" enabled=\"true\" focusable=\"true\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1054,1018][1504,1099]\" />
                    <node index=\"2\" text=\"二维码支付\" resource-id=\"\" class=\"android.widget.Button\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"true\" enabled=\"true\" focusable=\"true\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1185,1153][1374,1225]\" />
                    <node NAF=\"true\" index=\"3\" text=\"\" resource-id=\"\" class=\"android.widget.FrameLayout\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"true\" enabled=\"true\" focusable=\"true\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1531,483][1621,573]\" /></node>
            </node>
        </node>
        <node index=\"1\" text=\"\" resource-id=\"\" class=\"android.widget.FrameLayout\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1027,202][1531,247]\" /></node>
</hierarchy>
    '''

    param = {
        "xml": text,
        "query": "帮我交一下停车费",
    }
    res = rpa_func(param)
    print(json.dumps(res,     indent=4,ensure_ascii=False))

