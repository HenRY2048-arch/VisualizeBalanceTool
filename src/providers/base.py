"""提供商抽象基类和通用余额结果类"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import requests

log = logging.getLogger(__name__)


@dataclass
class BalanceResult:
    """余额查询结果"""
    balance: float | None = None
    is_available: bool | None = None
    currency: str = "CNY"
    kind: str = "balance"  # balance / cost
    initial: float = 0.0   # cost 模式：用户配置的初始余额
    spent: float = 0.0     # cost 模式：统计区间内的累计花费
    granted: float = 0.0
    topped_up: float = 0.0
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and self.balance is not None


class BaseProvider:
    """
    每个提供商只需继承此类并实现 parse_response()。
    其余逻辑（HTTP 请求、异常处理）由基类统一处理。
    """

    name: str = ""
    display_name: str = ""
    api_url: str = ""
    env_key_name: str = ""

    def __init__(self, cfg=None):
        # 部分提供商（如自定义 HTTP）需要读取额外配置
        self.cfg = cfg

    def headers(self, api_key: str) -> dict[str, str]:
        """默认使用 Bearer 认证，子类可覆盖。"""
        return {
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
        }

    # ------------------------------------------------------------------
    # 子类必须实现
    # ------------------------------------------------------------------

    def parse_response(self, data: dict[str, Any]) -> BalanceResult:
        """解析 API 返回的 JSON，提取余额信息"""
        raise NotImplementedError

    # ------------------------------------------------------------------
    # 基类统一实现
    # ------------------------------------------------------------------

    def check(self, api_key: str) -> BalanceResult:
        """执行一次余额查询（含网络请求和异常处理）"""
        if not api_key:
            return BalanceResult(error=f"未配置 {self.env_key_name}")

        try:
            resp = requests.get(self.api_url, headers=self.headers(api_key), timeout=10)
            log.info("[%s] HTTP %d | URL: %s", self.name, resp.status_code, self.api_url)
            log.debug("[%s] 响应: %s", self.name, resp.text[:500])

            if resp.status_code != 200:
                return BalanceResult(
                    error=f"[{self.name}] HTTP {resp.status_code}: {resp.text[:300]}"
                )

            return self.parse_response(resp.json())

        except requests.RequestException as exc:
            return BalanceResult(error=f"[{self.name}] 请求失败: {exc}")
        except (ValueError, KeyError, TypeError, IndexError) as exc:
            return BalanceResult(error=f"[{self.name}] 解析失败: {exc}")
