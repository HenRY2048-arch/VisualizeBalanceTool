"""Moonshot（Kimi）余额查询提供商"""

from __future__ import annotations

from typing import Any

from .base import BaseProvider, BalanceResult
from . import register


@register
class MoonshotProvider(BaseProvider):
    name = "moonshot"
    display_name = "Moonshot / Kimi"
    api_url = "https://api.moonshot.cn/v1/users/me/balance"
    env_key_name = "MOONSHOT_API_KEY"

    def parse_response(self, data: dict[str, Any]) -> BalanceResult:
        """
        响应形如：
        {
          "code": 0,
          "data": {
            "available_balance": 100.0,
            "voucher_balance": 20.0,
            "cash_balance": 80.0
          },
          "status": true
        }
        """
        payload = data.get("data") or {}
        if "available_balance" not in payload:
            return BalanceResult(error=f"[Moonshot] 响应中无 available_balance: {data}")

        def _num(key: str) -> float:
            try:
                return float(payload.get(key, 0) or 0)
            except (TypeError, ValueError):
                return 0.0

        return BalanceResult(
            balance=_num("available_balance"),
            is_available=True,
            currency="CNY",
            granted=_num("voucher_balance"),
            topped_up=_num("cash_balance"),
        )
