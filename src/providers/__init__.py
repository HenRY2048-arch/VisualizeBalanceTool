"""模型提供商注册表"""

from .base import BaseProvider, BalanceResult

_PROVIDERS: dict[str, type[BaseProvider]] = {}


def register(cls: type[BaseProvider]) -> type[BaseProvider]:
    """装饰器：注册一个提供商"""
    _PROVIDERS[cls.name] = cls
    return cls


def get_provider(name: str, cfg=None) -> BaseProvider:
    """根据名称获取提供商实例"""
    cls = _PROVIDERS.get(name)
    if cls is None:
        available = ", ".join(_PROVIDERS) or "(无)"
        raise ValueError(f"未知提供商: {name!r}，可用: {available}")
    return cls(cfg)


def available_providers() -> list[str]:
    return list(_PROVIDERS.keys())


# 触发各提供商模块的导入（注册）
from . import deepseek  # noqa: F401
from . import openai    # noqa: F401
from . import moonshot  # noqa: F401
from . import custom    # noqa: F401
