"""nl_repr模块移动到了aicore中。在这里import是为了保证向后兼容"""

from aicore.utils.nl_repr import (
    NLReprError,
    nl_repr,
    nl_repr_safe,
    set_bool_texts,
    set_list_params,
    register,
)