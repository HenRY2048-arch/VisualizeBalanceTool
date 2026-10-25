"""自定义 HTTP 余额提供商 — 用于没有内置适配的厂商"""

from __future__ import annotations

from typing import Any

from .base import BaseProvider, BalanceResult
from . import register


def _dig(data: Any, path: str):
    """按 a.b.c 的形式从嵌套字典中取值。"""
    current = data
    for part in [p for p in path.split(".") if p]:
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError):
                return None
        else:
            return None
        if current is None:
            return None
    return current


@register
class CustomProvider(BaseProvider):
    """
    通过配置指定任意余额接口：

      custom_api_url       余额接口地址
      custom_json_path     响应中余额字段的路径，如 data.balance
      custom_auth_header   认证头名称，默认 Authorization
      custom_auth_prefix   认证头前缀，默认 "Bearer "
      custom_currency      币种，默认 CNY
    """

    name = "custom"
    display_name = "自定义 HTTP"
    env_key_name = "CUSTOM_API_KEY"

    def __init__(self, cfg=None):
        super().__init__(cfg)
        get = cfg.get if cfg is not None else (lambda key, default=None: default)
        self.api_url = str(get("custom_api_url", "") or "")
        self.json_path = str(get("custom_json_path", "data.balance") or "data.balance")
        self.auth_header = str(get("custom_auth_header", "Authorization") or "Authorization")
        self.auth_prefix = str(get("custom_auth_prefix", "Bearer ") or "")
        self.currency = str(get("custom_currency", "CNY") or "CNY")

    def headers(self, api_key: str) -> dict[str, str]:
        return {
            self.auth_header: f"{self.auth_prefix}{api_key}",
            "Accept": "application/json",
        }

    def check(self, api_key: str) -> BalanceResult:
        if not self.api_url:
            return BalanceResult(error="未配置自定义余额接口地址（custom_api_url）")
        return super().check(api_key)

    def parse_response(self, data: dict[str, Any]) -> BalanceResult:
        value = _dig(data, self.json_path)
        if value is None:
            return BalanceResult(error=f"[自定义] 响应中找不到字段 {self.json_path}")
        try:
            balance = float(value)
        except (TypeError, ValueError):
            return BalanceResult(error=f"[自定义] 字段 {self.json_path} 不是数字: {value!r}")
        return BalanceResult(balance=balance, is_available=True, currency=self.currency)
