"""OpenAI 余额查询提供商"""

from __future__ import annotations

from typing import Any

from .base import BaseProvider, BalanceResult
from . import register


@register
class OpenAIProvider(BaseProvider):
    name = "openai"
    display_name = "OpenAI"
    api_url = "https://api.openai.com/v1/organization/limits"
    env_key_name = "OPENAI_API_KEY"

    def parse_response(self, data: dict[str, Any]) -> BalanceResult:
        """
        OpenAI /v1/organization/limits 响应格式：
        {
            "data": [
                {
                    "name": "hard_limit",
                    "value": 120.0,
                    "...
                }
            ]
        }
        注：OpenAI 没有直接的余额接口，此接口返回账户限额信息。
        """
        items = data.get("data", [])
        if not items:
            return BalanceResult(error="[OpenAI] 响应中无 data 字段")

        # 从 limit 信息中提取可用额度
        # OpenAI 的 limits 接口返回的是限制而非余额，这里做近似处理
        hard_limit = 0.0
        for item in items:
            if item.get("name") == "hard_limit":
                hard_limit = float(item.get("value", 0))
                break

        if hard_limit > 0:
            return BalanceResult(
                balance=hard_limit,
                is_available=True,
                currency="USD",
            )

        return BalanceResult(
            balance=0.0,
            is_available=False,
            currency="USD",
            error="[OpenAI] 未能获取有效限额信息",
        )
