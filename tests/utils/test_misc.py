import pytest

from typing import Final

from aicore.utils.misc import safe_update

def test_safe_update():
    d1 = {'x': 1}
    d2 = {'y': 2}
    safe_update(d1, d2)  # 成功

    with pytest.raises(KeyError):
        safe_update(d1, {'x': 3})  # 抛出 KeyError



RUN_PYTEST: Final = False

if __name__ == "__main__":
    if RUN_PYTEST:
        # 使用 -s 参数禁用输出捕获，这样可以看到print输出
        pytest.main(["-vs", __file__])
    else:
        test_safe_update()
        
