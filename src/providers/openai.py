"""OpenAI 花费统计提供商。

OpenAI 没有正式的余额公开接口，这里用「初始余额 - 累计花费」估算剩余额度：

  剩余 = openai_initial_balance - sum(costs 从 openai_costs_start_date 到 now)

数据来自 GET /v1/organization/costs，需要 Admin API Key（sk-admin- 开头）。
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

import requests

from .base import BaseProvider, BalanceResult
from . import register

log = logging.getLogger(__name__)


def _parse_date(value: str) -> int:
    """把 YYYY-MM-DD 转成 Unix 秒；空值返回 0（表示从最早开始，自动分页）。"""
    value = (value or "").strip()
    if not value:
        return 0
    try:
        dt = datetime.strptime(value, "%Y-%m-%d")
        return int(dt.replace(tzinfo=timezone.utc).timestamp())
    except ValueError:
        return 0


@register
class OpenAIProvider(BaseProvider):
    name = "openai"
    display_name = "OpenAI（花费统计）"
    api_url = "https://api.openai.com/v1/organization/costs"
    env_key_name = "OPENAI_ADMIN_KEY"

    def __init__(self, cfg=None):
        super().__init__(cfg)
        get = cfg.get if cfg is not None else (lambda key, default=None: default)
        try:
            self.initial = float(get("openai_initial_balance", 0.0) or 0)
        except (TypeError, ValueError):
            self.initial = 0.0
        self.start_time = _parse_date(str(get("openai_costs_start_date", "") or ""))
        try:
            self.fallback_days = min(max(int(float(get("openai_costs_days", 7))), 1), 180)
        except (TypeError, ValueError):
            self.fallback_days = 7

    def check(self, api_key: str) -> BalanceResult:
        if not api_key:
            return BalanceResult(error=f"未配置 {self.env_key_name}")

        end = int(time.time())
        start = self.start_time if self.start_time > 0 else end - self.fallback_days * 86400
        total = 0.0

        try:
            cursor: str | None = None
            for _page in range(100):  # 分页安全上限
                params: dict[str, Any] = {
                    "start_time": start,
                    "end_time": end,
                    "bucket_width": "1d",
                    "limit": 180,
                }
                if cursor:
                    params["page"] = cursor
                resp = requests.get(
                    self.api_url, headers=self.headers(api_key), params=params, timeout=20
                )
                if resp.status_code != 200:
                    return BalanceResult(
                        error=f"[openai] HTTP {resp.status_code}: {resp.text[:300]}"
                    )
                data = resp.json()
                total += self._sum_buckets(data)
                if not data.get("has_more"):
                    break
                cursor = data.get("next_page")
                if not cursor:
                    break
        except requests.RequestException as exc:
            return BalanceResult(error=f"[openai] 请求失败: {exc}")
        except (ValueError, KeyError, TypeError, IndexError) as exc:
            return BalanceResult(error=f"[openai] 解析失败: {exc}")

        spent = round(total, 4)
        remaining = round(self.initial - spent, 4)
        return BalanceResult(
            balance=remaining,
            is_available=True,
            currency="USD",
            initial=self.initial,
            spent=spent,
        )

    @staticmethod
    def _sum_buckets(data: dict[str, Any]) -> float:
        total = 0.0
        for bucket in data.get("data", []):
            for item in bucket.get("results", []):
                amount = item.get("amount") or {}
                try:
                    total += float(amount.get("value", 0))
                except (TypeError, ValueError):
                    continue
        return total

    def parse_response(self, data: dict[str, Any]) -> BalanceResult:
        spent = round(self._sum_buckets(data), 4)
        return BalanceResult(
            balance=round(self.initial - spent, 4),
            is_available=True,
            currency="USD",
            initial=self.initial,
            spent=spent,
        )
