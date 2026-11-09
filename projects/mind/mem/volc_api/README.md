# 火山记忆库功能说明

volc_api包封装了火山记忆库功能的API调用。其python接口基于pydantic数据模型，提供了类型检查和数据验证。除了更加好读好用，也是跟内部其它功能的交互接口。

- [_api.py](./_api.py): 封装了火山引擎API的通用请求和响应模型。
- [collection.py](./collection.py): 对于记忆库部分API的结构化封装。详情参见[API文档](https://www.volcengine.com/docs/84313/1783347?lang=zh)和[测试用例](../tests/volc_api/test_collection.py)。
- [session.py](./session.py): 对于会话部分API的结构化封装。详情参见[API文档](https://www.volcengine.com/docs/84313/1783353?lang=zh)和[测试用例](../tests/volc_api/test_session.py)。  
- [retrieval.py](./retrieval.py): 对于记忆检索部分API的结构化封装。详情参见[API文档](https://www.volcengine.com/docs/84313/1783351?lang=zh)和[测试用例](../tests/volc_api/test_retrieval.py)。  
