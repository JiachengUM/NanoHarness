import pyjexl
jexl = pyjexl.JEXL()
# 仅允许访问 context 中显式提供的字段
context = {"user": {"name": "Alice", "age": 25}}
result = jexl.evaluate("user.name + ' is ' + (user.age > 18 ? 'adult' : 'minor')", context)
# 若表达式包含未注册字段（如 user.role），执行将失败