
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

    button_bounds_pattern = r'<node[^>]*text="确认订单"[^>]*bounds="([^"]+)"'
    button_bounds_match = re.search(button_bounds_pattern, xml)
    button_bounds = button_bounds_match.group(1) if button_bounds_match else ""
    coordinates = bounds_to_coordinates(button_bounds)
    if coordinates is None:
        return {"code": 1}
    else:
        return {
            "code": 0,
            "thought": f"当前页面是确认订单页面，上一步用户已经确认了订单，所以下一步应该点击“确认订单”按钮进行缴费",
            "actions": [{
                "action": "click",
                "name": "确认订单",
                "coordinates": coordinates,
            }],
            "task_status": "确认缴费"
        }

if __name__ == '__main__':

    # 待处理的字符串
    text = '''
    <?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
<hierarchy rotation=\"1\">
    <node index=\"0\" text=\"\" resource-id=\"\" class=\"android.widget.FrameLayout\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[901,202][1658,1542]\">
        <node index=\"0\" text=\"\" resource-id=\"\" class=\"android.widget.FrameLayout\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"true\" enabled=\"true\" focusable=\"true\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[901,202][1658,1542]\">
            <node index=\"0\" text=\"\" resource-id=\"\" class=\"android.widget.RelativeLayout\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[901,202][1658,1542]\">
                <node index=\"0\" text=\"\" resource-id=\"\" class=\"android.widget.LinearLayout\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[901,247][1000,355]\">
                    <node index=\"0\" text=\"\" resource-id=\"\" class=\"android.widget.Button\" package=\"com.tencent.wmpf\" content-desc=\"返回\" checkable=\"false\" checked=\"false\" clickable=\"true\" enabled=\"true\" focusable=\"true\" focused=\"false\" scrollable=\"false\" long-clickable=\"true\" password=\"false\" selected=\"false\" bounds=\"[937,274][964,328]\" /></node>
                <node index=\"1\" text=\"订单确认\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"true\" enabled=\"true\" focusable=\"true\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1203,247][1355,355]\" />
                <node index=\"2\" text=\"\" resource-id=\"\" class=\"android.widget.FrameLayout\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"true\" password=\"false\" selected=\"false\" bounds=\"[901,355][1658,1542]\">
                    <node index=\"0\" text=\"\" resource-id=\"\" class=\"android.widget.FrameLayout\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"true\" enabled=\"true\" focusable=\"true\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[901,355][1658,1542]\">
                        <node index=\"0\" text=\"\" resource-id=\"\" class=\"android.widget.FrameLayout\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[901,355][1658,1542]\">
                            <node index=\"0\" text=\"\" resource-id=\"\" class=\"android.webkit.WebView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"true\" focused=\"true\" scrollable=\"true\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[901,355][1661,1543]\">
                                <node index=\"0\" text=\"\" resource-id=\"\" class=\"android.view.View\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[901,355][1661,1543]\">
                                    <node index=\"0\" text=\"\" resource-id=\"\" class=\"android.view.View\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[901,355][1661,1543]\">
                                        <node index=\"0\" text=\"\" resource-id=\"\" class=\"android.view.View\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[901,355][1661,1543]\">
                                            <node index=\"0\" text=\"\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[914,368][1661,1543]\" />
                                            <node index=\"1\" text=\"\" resource-id=\"\" class=\"android.view.View\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[914,368][1645,784]\">
                                                <node index=\"0\" text=\"￥565\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[914,400][1645,505]\" />
                                                <node index=\"1\" text=\"已停 18天4小时13分钟\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[914,503][1645,548]\" />
                                                <node index=\"2\" text=\"停车场\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[914,577][1031,618]\" />
                                                <node index=\"3\" text=\"捷停车智慧停车场\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1087,577][1645,618]\" />
                                                <node index=\"4\" text=\"车牌号码\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[914,645][1058,685]\" />
                                                <node index=\"5\" text=\"鄂-A12456\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1087,645][1645,685]\" />
                                                <node index=\"6\" text=\"入场时间\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[914,712][1058,753]\" />
                                                <node index=\"7\" text=\"2025-09-29 12:51\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1087,712][1645,753]\" /></node>
                                            <node index=\"2\" text=\"\" resource-id=\"\" class=\"android.view.View\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[914,805][1645,973]\">
                                                <node index=\"0\" text=\"\" resource-id=\"\" class=\"android.view.View\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[914,823][1645,888]\">
                                                    <node index=\"0\" text=\"优惠券\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[946,823][1031,888]\" />
                                                    <node index=\"1\" text=\"暂无优惠券\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1443,823][1580,888]\" />
                                                    <node index=\"2\" text=\"\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1573,834][1614,877]\" /></node>
                                                <node index=\"2\" text=\"\" resource-id=\"\" class=\"android.view.View\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[946,899][1067,942]\">
                                                    <node index=\"0\" text=\"停车币\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[946,901][1031,942]\" />
                                                    <node index=\"1\" text=\"\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1029,904][1069,944]\" /></node>
                                                <node index=\"3\" text=\"共0个，满500可用\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1389,899][1614,942]\" /></node>
                                            <node index=\"3\" text=\"\" resource-id=\"\" class=\"android.view.View\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[914,994][1645,1212]\">
                                                <node index=\"0\" text=\"\" resource-id=\"\" class=\"android.view.View\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[914,994][1645,1212]\">
                                                    <node index=\"0\" text=\"8元购停车券*KFC劲脆鸡腿堡兑换券\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[941,994][1301,1054]\" />
                                                    <node index=\"1\" text=\"\" resource-id=\"\" class=\"android.view.View\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[919,1052][1643,1210]\">
                                                        <node index=\"0\" text=\"\" resource-id=\"\" class=\"android.view.View\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[939,1084][1621,1180]\">
                                                            <node index=\"0\" text=\"\" resource-id=\"\" class=\"android.widget.Image\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[939,1099][1027,1165]\" />
                                                            <node index=\"1\" text=\"本单立减2元\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1040,1084][1366,1131]\" />
                                                            <node index=\"2\" text=\"2元*4张停车券+KFC劲脆鸡腿堡兑换券\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1040,1142][1324,1176]\" />
                                                            <node index=\"3\" text=\"￥8\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1468,1088][1542,1147]\" />
                                                            <node index=\"4\" text=\"￥28.50\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1468,1142][1542,1174]\" />
                                                            <node index=\"5\" text=\"\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1555,1084][1621,1180]\" /></node>
                                                    </node>
                                                </node>
                                            </node>
                                            <node index=\"4\" text=\"\" resource-id=\"\" class=\"android.view.View\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[914,1232][1645,1543]\">
                                                <node index=\"0\" text=\"该车场未开通电子发票，请向物业方索要发票\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[914,1264][1645,1338]\" />
                                                <node index=\"1\" text=\"费用明细\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[946,1365][1058,1408]\" />
                                                <node index=\"2\" text=\"停车费￥565.00\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1054,1365][1614,1408]\" />
                                                <node index=\"3\" text=\"费用总计：￥565.00\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[946,1426][1614,1516]\" /></node>
                                            <node index=\"5\" text=\"\" resource-id=\"\" class=\"android.view.View\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[901,1345][1661,1543]\">
                                                <node index=\"0\" text=\"请于3分钟内付款，超时将重新计算停车费用\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1076,1347][1519,1405]\" />
                                                <node index=\"1\" text=\"\" resource-id=\"\" class=\"android.view.View\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[901,1403][1661,1543]\">
                                                    <node index=\"0\" text=\"\" resource-id=\"\" class=\"android.view.View\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[930,1403][1132,1543]\">
                                                        <node index=\"0\" text=\"合计￥565.00\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[930,1441][1132,1507]\" /></node>
                                                    <node index=\"1\" text=\"确认订单\" resource-id=\"\" class=\"android.widget.TextView\" package=\"com.tencent.wmpf\" content-desc=\"\" checkable=\"false\" checked=\"false\" clickable=\"false\" enabled=\"true\" focusable=\"false\" focused=\"false\" scrollable=\"false\" long-clickable=\"false\" password=\"false\" selected=\"false\" bounds=\"[1292,1423][1630,1525]\" /></node>
                                            </node>
                                        </node>
                                    </node>
                                </node>
                            </node>
                        </node>
                    </node>
                </node>
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

