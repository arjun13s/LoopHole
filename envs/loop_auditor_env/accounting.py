"""Per-run token meter — the single place 'context used / cost per call' is tracked.

OWNER: Claude. Pure, no hud/network. The Y reward's lambda term reads `meter.spent`;
`get_budget()` exposes it to the agent.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field


def estimate_tokens(text) -> int:
    """Rough token estimate (~4 chars/token). None -> 0; non-str -> json-stringified."""
    if text is None:
        return 0
    if not isinstance(text, str):
        text = json.dumps(text, default=str)
    return max(1, len(text) // 4)


@dataclass
class TokenMeter:
    budget: "int | None" = None
    spent: int = 0
    breakdown: dict = field(default_factory=dict)

    def charge(self, amount: int, category: str) -> int:
        amount = max(0, int(amount))
        self.spent += amount
        self.breakdown[category] = self.breakdown.get(category, 0) + amount
        return self.spent

    @property
    def remaining(self) -> "int | None":
        if self.budget is None:
            return None
        return max(0, self.budget - self.spent)
