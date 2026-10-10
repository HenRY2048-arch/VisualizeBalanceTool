"""DeepSeek 余额查询提供商"""

from __future__ import annotations

from typing import Any

from .base import BaseProvider, BalanceResult
from . import register


@register
class DeepSeekProvider(BaseProvider):
    name = "deepseek"
    display_name = "DeepSeek"
    api_url = "https://api.deepseek.com/user/balance"
    env_key_name = "DEEPSEEK_API_KEY"

    def parse_response(self, data: dict[str, Any]) -> BalanceResult:
        """
        DeepSeek 响应格式：
        {
            "is_available": true,
            "balance_infos": [
                {
                    "currency": "CNY",
                    "total_balance": "8.96",
                    "granted_balance": "0.00",
                    "topped_up_balance": "8.96"
                }
            ]
        }
        """
        is_available = data.get("is_available", False)
        balance_infos = data.get("balance_infos", [])
        if not balance_infos:
            return BalanceResult(error=f"[DeepSeek] 响应中无 balance_infos: {data}")

        info = balance_infos[0]
        return BalanceResult(
            balance=float(info.get("total_balance", 0)),
            is_available=is_available,
            currency=info.get("currency", "CNY"),
            granted=float(info.get("granted_balance", 0)),
            topped_up=float(info.get("topped_up_balance", 0)),
        )
