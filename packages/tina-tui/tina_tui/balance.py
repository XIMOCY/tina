"""账户余额

配合 ``BaseAPI.fetch_balance()`` 使用：解析 DeepSeek 风格的
``GET /user/balance`` 返回，并格式化成能直接显示的一小段文字。

用它算「本轮花了多少」不需要维护单价表——直接取两次余额的差值即可
（代价是精度受服务端小数点位数限制，且同一账号下的其它会话也会算进来）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Balance:
    """账户余额"""

    currency: str
    total: float
    granted: float = 0.0
    topped_up: float = 0.0

    def format(self) -> str:
        """格式化成 `¥2.96`（非人民币时带上币种）"""
        if self.currency.upper() == "CNY":
            return f"¥{self.total:.2f}"
        return f"{self.total:.2f} {self.currency}".strip()


def parse_balance(data: Any) -> Balance | None:
    """解析余额接口返回；拿不到可用数据时返回 None"""
    if not isinstance(data, dict):
        return None
    infos = data.get("balance_infos")
    if not isinstance(infos, list) or not infos:
        return None
    info = infos[0]
    if not isinstance(info, dict):
        return None
    try:
        total = float(info.get("total_balance") or 0)
    except (TypeError, ValueError):
        return None
    try:
        granted = float(info.get("granted_balance") or 0)
        topped_up = float(info.get("topped_up_balance") or 0)
    except (TypeError, ValueError):
        granted = topped_up = 0.0
    return Balance(
        currency=str(info.get("currency") or ""),
        total=total,
        granted=granted,
        topped_up=topped_up,
    )


def format_cost(amount: float) -> str:
    """把一轮的花费格式化成 `¥0.12` / `¥<0.01`

    余额只到分，所以小于一分钱只能显示成 `¥<0.01`，不能假装是 0。
    """
    if amount <= 0:
        return "¥0.00"
    if amount < 0.005:
        return "¥<0.01"
    return f"¥{amount:.2f}"
