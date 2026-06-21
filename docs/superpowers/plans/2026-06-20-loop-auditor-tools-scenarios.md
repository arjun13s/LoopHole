# Loop-Auditor Tools & Scenarios Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build out the Loop-Auditor HUD v6 env's agent-facing tools and task scenarios (static audit X + replay-based gate Y) before any training.

**Architecture:** Approach 1 — two `@env.template` tasks (`audit-trace`, `gate-trace`) sharing pure tools (`tools.py`), a token meter (`accounting.py`), reward functions (`reward.py`), and a scenarios layer (`scenarios.py`). Stateful tools (budget/solution/observe_next/gate) live in `env.py` and charge a per-run `TokenMeter`. X stays a standalone floor; Y replays Person 1's recorded traces iteration-by-iteration.

**Tech Stack:** Python 3.11/3.12, hud-python 0.6.x, fastmcp, pytest + pytest-asyncio. Spec: `docs/superpowers/specs/2026-06-20-loop-auditor-tools-scenarios-design.md`.

## Global Constraints

- Python `>=3.11,<3.13`; run everything in the repo venv: `/Users/arjunsingh/LoopHole/.venv/bin/python`.
- All env modules use the **dual-import** convention: `try: from . import X` / `except ImportError: import X` (package for pytest, flat for `hud serve env:env`).
- **X reward (`compute_reward`, §1.4) is frozen — do not change it.** New cost behavior goes in `compute_gate_reward` (Y) and the optional `LAMBDA_X` knob (default `0.0`).
- Pure modules (`accounting`, `tools`, `reward`, `scenarios`) must have **no hud import and no network**.
- Tests are **keyless**: set `LOOP_AUDITOR_JUDGE_STUB=1`; env tests `pytest.importorskip("hud")`.
- Tests live in `envs/loop_auditor_env/tests/`; imports use the `loop_auditor_env` package (root `pyproject.toml` sets `pythonpath=["envs"]`, `asyncio_mode="auto"`).
- Run tests from repo root: `cd /Users/arjunsingh/LoopHole && .venv/bin/python -m pytest -q`.
- Commit after each task. End commit messages with the Co-Authored-By trailer.
- Trace shape (from `fixtures/*.json`): `{run_id, task, iterations:[{index, thought?, steps:[{step_id, action_type, tool_name?, input?, output?, status, tokens}]}], planted_failure: {step_id, failure_type, description} | null}`.

---

### Task 1: Token meter (`accounting.py`)

**Files:**
- Create: `envs/loop_auditor_env/accounting.py`
- Test: `envs/loop_auditor_env/tests/test_accounting.py`

**Interfaces:**
- Produces: `estimate_tokens(text) -> int`; `TokenMeter(budget: int|None=None)` with `.spent:int`, `.breakdown:dict`, `.charge(amount:int, category:str)->int`, `.remaining -> int|None`.

- [ ] **Step 1: Write the failing test**

```python
# envs/loop_auditor_env/tests/test_accounting.py
from loop_auditor_env.accounting import TokenMeter, estimate_tokens


def test_estimate_tokens():
    assert estimate_tokens(None) == 0
    assert estimate_tokens("") == 1          # min 1 for non-None
    assert estimate_tokens("a" * 40) == 10   # len//4
    assert estimate_tokens({"a": 1}) >= 1     # non-str is json-stringified


def test_charge_accumulates_and_breaks_down():
    m = TokenMeter()
    m.charge(10, "trace")
    m.charge(5, "tool")
    m.charge(3, "trace")
    assert m.spent == 18
    assert m.breakdown == {"trace": 13, "tool": 5}


def test_charge_floors_negative_and_returns_spent():
    m = TokenMeter()
    assert m.charge(-7, "x") == 0
    assert m.spent == 0


def test_remaining():
    assert TokenMeter().remaining is None
    m = TokenMeter(budget=100)
    m.charge(30, "x")
    assert m.remaining == 70
    m.charge(1000, "x")
    assert m.remaining == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/arjunsingh/LoopHole && .venv/bin/python -m pytest envs/loop_auditor_env/tests/test_accounting.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'loop_auditor_env.accounting'`

- [ ] **Step 3: Write minimal implementation**

```python
# envs/loop_auditor_env/accounting.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/arjunsingh/LoopHole && .venv/bin/python -m pytest envs/loop_auditor_env/tests/test_accounting.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add envs/loop_auditor_env/accounting.py envs/loop_auditor_env/tests/test_accounting.py
git commit -m "feat(env): add TokenMeter for per-run cost accounting" -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Pure inspection tools (`tools.py`)

**Files:**
- Modify: `envs/loop_auditor_env/tools.py` (append new functions)
- Test: `envs/loop_auditor_env/tests/test_tools_extra.py`

**Interfaces:**
- Consumes: existing `get_step(trace, step_id)` in `tools.py`.
- Produces: `search_steps(trace, query) -> list[dict]`; `get_errors(trace) -> list[dict]`; `get_step_io(trace, step_id) -> dict`; `get_reference_solution(trace) -> str | None`.

- [ ] **Step 1: Write the failing test**

```python
# envs/loop_auditor_env/tests/test_tools_extra.py
import json
from pathlib import Path

from loop_auditor_env import config
from loop_auditor_env.tools import (
    get_errors,
    get_reference_solution,
    get_step_io,
    search_steps,
)


def _trace():
    p = sorted((config.FIXTURES_DIR).glob("buggy_routing*.json"))[0]
    return json.loads(Path(p).read_text())


def test_search_steps_matches_tool_and_io_case_insensitive():
    t = _trace()
    hits = search_steps(t, "ADMIN")  # appears in input/output of the planted step
    assert any(s["step_id"] == "iter0.step1.edit-admin-route" for s in hits)


def test_search_steps_no_match_returns_empty():
    assert search_steps(_trace(), "zzzzz-nope") == []


def test_get_errors_filters_status():
    t = {"iterations": [{"index": 0, "steps": [
        {"step_id": "a", "action_type": "tool_call", "status": "ok"},
        {"step_id": "b", "action_type": "tool_call", "status": "error"},
        {"step_id": "c", "action_type": "tool_call", "status": "timeout"},
    ]}]}
    ids = [s["step_id"] for s in get_errors(t)]
    assert ids == ["b", "c"]


def test_get_step_io_returns_untruncated():
    t = _trace()
    io = get_step_io(t, "iter0.step1.edit-admin-route")
    assert io["step_id"] == "iter0.step1.edit-admin-route"
    assert "admin" in str(io["output"]).lower()


def test_get_reference_solution_absent_is_none():
    assert get_reference_solution(_trace()) is None


def test_get_reference_solution_present():
    assert get_reference_solution({"reference_solution": "edit customer checkout"}) == "edit customer checkout"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/arjunsingh/LoopHole && .venv/bin/python -m pytest envs/loop_auditor_env/tests/test_tools_extra.py -q`
Expected: FAIL — `ImportError: cannot import name 'search_steps'`

- [ ] **Step 3: Write minimal implementation** (append to `envs/loop_auditor_env/tools.py`)

```python
import json as _json


def _iter_steps(trace: dict):
    if not isinstance(trace, dict):
        raise TypeError("trace must be a dict")
    for iteration in trace.get("iterations", []) or []:
        if isinstance(iteration, dict):
            for step in iteration.get("steps", []) or []:
                if isinstance(step, dict):
                    yield step


def _haystack(step: dict) -> str:
    parts = []
    for key in ("tool_name", "input", "output"):
        v = step.get(key)
        if v is None:
            continue
        parts.append(v if isinstance(v, str) else _json.dumps(v, default=str))
    return " ".join(parts).lower()


def search_steps(trace: dict, query: str) -> list:
    """Steps whose tool_name/input/output contains `query` (case-insensitive)."""
    q = str(query).lower()
    return [s for s in _iter_steps(trace) if q in _haystack(s)]


def get_errors(trace: dict) -> list:
    """Steps with status in {error, timeout} (often near the fault)."""
    return [s for s in _iter_steps(trace) if s.get("status") in ("error", "timeout")]


def get_step_io(trace: dict, step_id: str) -> dict:
    """Untruncated input/output for a step. Raises KeyError if not found."""
    s = get_step(trace, step_id)
    return {"step_id": s["step_id"], "input": s.get("input"), "output": s.get("output")}


def get_reference_solution(trace: dict) -> "str | None":
    """Task reference solution if the trace carries one (Person 1 may add it)."""
    ref = (trace or {}).get("reference_solution")
    return ref if isinstance(ref, str) and ref.strip() else None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/arjunsingh/LoopHole && .venv/bin/python -m pytest envs/loop_auditor_env/tests/test_tools_extra.py -q`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add envs/loop_auditor_env/tools.py envs/loop_auditor_env/tests/test_tools_extra.py
git commit -m "feat(env): add search_steps/get_errors/get_step_io/get_reference_solution" -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Gate reward (`reward.py`, `config.py`)

**Files:**
- Modify: `envs/loop_auditor_env/config.py` (add λ constants)
- Modify: `envs/loop_auditor_env/reward.py` (append `compute_gate_reward`)
- Test: `envs/loop_auditor_env/tests/test_gate_reward.py`

**Interfaces:**
- Consumes: `config.LAMBDA_TOKENS`, `config.NO_FAULT_TYPE`.
- Produces: `compute_gate_reward(decision, stop_iteration, fault_iteration, tokens_spent, flagged_failure_type=None, planted_failure_type=None, lambda_tokens=None) -> float`. `decision ∈ {"flag","stop","completed"}`.

- [ ] **Step 1: Write the failing test**

```python
# envs/loop_auditor_env/tests/test_gate_reward.py
from loop_auditor_env.reward import compute_gate_reward as g


def test_buggy_flag_at_fault_max():
    r = g("flag", stop_iteration=2, fault_iteration=2, tokens_spent=0,
          flagged_failure_type="routing", planted_failure_type="routing", lambda_tokens=0.0)
    assert r == 1.3  # detect 1.0 + type 0.3


def test_buggy_flag_after_fault_costs_more_tokens():
    early = g("flag", 2, 2, tokens_spent=10, planted_failure_type="routing", lambda_tokens=0.01)
    late = g("flag", 4, 2, tokens_spent=30, planted_failure_type="routing", lambda_tokens=0.01)
    assert early > late  # both detect, but later burned more tokens


def test_buggy_flag_before_fault_misses():
    assert g("flag", 0, 2, tokens_spent=5, lambda_tokens=0.0) == 0.0


def test_buggy_completed_without_flag_misses():
    assert g("completed", None, 2, tokens_spent=50, lambda_tokens=0.0) == 0.0


def test_clean_completed_rewarded():
    assert g("completed", None, None, tokens_spent=0, lambda_tokens=0.0) == 1.0


def test_clean_false_flag_penalized():
    assert g("flag", 1, None, tokens_spent=5, lambda_tokens=0.0) == 0.0


def test_lambda_reduces_reward():
    assert g("completed", None, None, tokens_spent=100, lambda_tokens=0.001) == 0.9
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/arjunsingh/LoopHole && .venv/bin/python -m pytest envs/loop_auditor_env/tests/test_gate_reward.py -q`
Expected: FAIL — `ImportError: cannot import name 'compute_gate_reward'`

- [ ] **Step 3a: Add config constants** (in `envs/loop_auditor_env/config.py`, after the reward-weights block)

```python
# --- gate (Design Y) + cost knobs (env-overridable) --------------------------
LAMBDA_TOKENS = float(os.environ.get("LOOP_AUDITOR_LAMBDA_TOKENS", "0.001"))
LAMBDA_X = float(os.environ.get("LOOP_AUDITOR_LAMBDA_X", "0.0"))  # 0 honors frozen §1.4
SOLUTION_COST = int(os.environ.get("LOOP_AUDITOR_SOLUTION_COST", "300"))
GATE_TURN_LIMIT = int(os.environ.get("LOOP_AUDITOR_GATE_TURN_LIMIT", "32"))
```

- [ ] **Step 3b: Append `compute_gate_reward`** (to `envs/loop_auditor_env/reward.py`)

```python
def compute_gate_reward(
    decision: str,
    stop_iteration: "int | None",
    fault_iteration: "int | None",
    tokens_spent: int,
    flagged_failure_type: "str | None" = None,
    planted_failure_type: "str | None" = None,
    lambda_tokens: "float | None" = None,
) -> float:
    """Design Y reward. decision in {'flag','stop','completed'}.

    Buggy (fault_iteration is not None): caught = flagged at/after the fault ->
        1.0 + 0.3*(flagged_failure_type == planted_failure_type) - lambda*tokens.
    Clean (fault_iteration is None): completed with no flag/stop -> 1.0 - lambda*tokens,
        else 0.0 - lambda*tokens (false abort).
    """
    lam = config.LAMBDA_TOKENS if lambda_tokens is None else lambda_tokens
    penalty = lam * max(0, int(tokens_spent))

    if fault_iteration is None:  # clean trace
        base = 1.0 if decision == "completed" else 0.0
        return base - penalty

    caught = (
        decision == "flag"
        and stop_iteration is not None
        and stop_iteration >= fault_iteration
    )
    base = 1.0 if caught else 0.0
    if caught and flagged_failure_type is not None and flagged_failure_type == planted_failure_type:
        base += 0.3
    return base - penalty
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/arjunsingh/LoopHole && .venv/bin/python -m pytest envs/loop_auditor_env/tests/test_gate_reward.py -q`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add envs/loop_auditor_env/config.py envs/loop_auditor_env/reward.py envs/loop_auditor_env/tests/test_gate_reward.py
git commit -m "feat(env): add compute_gate_reward (Y) + lambda/cost config" -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Scenarios (`scenarios.py`, `config.py`)

**Files:**
- Modify: `envs/loop_auditor_env/config.py` (add `DEFAULT_ENABLED_TOOLS`)
- Create: `envs/loop_auditor_env/scenarios.py`
- Test: `envs/loop_auditor_env/tests/test_scenarios.py`

**Interfaces:**
- Consumes: `config.DEFAULT_ENABLED_TOOLS`, `config.LAMBDA_TOKENS`, `config.GATE_TURN_LIMIT`.
- Produces: `Scenario(id, trace_id, mode, enabled_tools, lambda_tokens=0.0, token_budget=None, turn_limit=None)`; `fault_iteration(trace) -> int | None`; `enumerate_scenarios(traces, solution_ablation=False) -> list[Scenario]`.

- [ ] **Step 1: Write the failing test**

```python
# envs/loop_auditor_env/tests/test_scenarios.py
from loop_auditor_env.scenarios import Scenario, enumerate_scenarios, fault_iteration

BUGGY = {"run_id": "b1", "iterations": [
    {"index": 0, "steps": [{"step_id": "iter0.step0", "action_type": "tool_call"}]},
    {"index": 1, "steps": [{"step_id": "iter1.step0.bad", "action_type": "tool_call"}]},
], "planted_failure": {"step_id": "iter1.step0.bad", "failure_type": "routing", "description": "x"}}
CLEAN = {"run_id": "c1", "iterations": [{"index": 0, "steps": [{"step_id": "iter0.step0", "action_type": "message"}]}], "planted_failure": None}


def test_fault_iteration_locates_planted_step():
    assert fault_iteration(BUGGY) == 1
    assert fault_iteration(CLEAN) is None


def test_enumerate_makes_audit_and_gate_per_trace():
    scs = enumerate_scenarios([BUGGY, CLEAN])
    ids = {s.id for s in scs}
    assert ids == {"audit__b1", "gate__b1", "audit__c1", "gate__c1"}
    gate = next(s for s in scs if s.id == "gate__b1")
    assert gate.mode == "gate" and gate.turn_limit is not None
    assert "get_solution" not in gate.enabled_tools  # off by default


def test_solution_ablation_adds_variant_with_tool_on():
    scs = enumerate_scenarios([BUGGY], solution_ablation=True)
    on = next(s for s in scs if s.id == "audit__b1__solution_on")
    assert "get_solution" in on.enabled_tools
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/arjunsingh/LoopHole && .venv/bin/python -m pytest envs/loop_auditor_env/tests/test_scenarios.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'loop_auditor_env.scenarios'`

- [ ] **Step 3a: Add config default** (in `config.py`, after the gate knobs)

```python
DEFAULT_ENABLED_TOOLS = frozenset({
    "get_trace_summary", "get_iteration", "get_step",
    "search_steps", "get_errors", "get_step_io",
    "get_budget", "observe_next", "gate",
})  # get_solution OFF by default; scenarios opt it in
```

- [ ] **Step 3b: Create `scenarios.py`**

```python
# envs/loop_auditor_env/scenarios.py
"""Scenario definitions: which trace, which mode (audit/gate), which tools.

OWNER: Claude. Pure, no hud/network.
"""

from __future__ import annotations

from dataclasses import dataclass, field

try:  # package (pytest) | flat (hud)
    from . import config
except ImportError:
    import config


@dataclass(frozen=True)
class Scenario:
    id: str
    trace_id: str
    mode: str  # "audit" | "gate"
    enabled_tools: frozenset = field(default_factory=frozenset)
    lambda_tokens: float = 0.0
    token_budget: "int | None" = None
    turn_limit: "int | None" = None


def fault_iteration(trace: dict) -> "int | None":
    """Iteration index containing the planted fault, or None for a clean trace."""
    pf = (trace or {}).get("planted_failure")
    if not pf:
        return None
    sid = pf["step_id"]
    for it in trace.get("iterations", []) or []:
        if any(s.get("step_id") == sid for s in it.get("steps", []) or []):
            return it["index"]
    return None


def enumerate_scenarios(traces, solution_ablation: bool = False) -> list:
    """One audit + one gate scenario per trace; optional get_solution ablation."""
    out = []
    for t in traces:
        rid = t["run_id"]
        out.append(Scenario(id=f"audit__{rid}", trace_id=rid, mode="audit",
                            enabled_tools=config.DEFAULT_ENABLED_TOOLS, lambda_tokens=config.LAMBDA_X))
        out.append(Scenario(id=f"gate__{rid}", trace_id=rid, mode="gate",
                            enabled_tools=config.DEFAULT_ENABLED_TOOLS,
                            lambda_tokens=config.LAMBDA_TOKENS, turn_limit=config.GATE_TURN_LIMIT))
        if solution_ablation:
            out.append(Scenario(id=f"audit__{rid}__solution_on", trace_id=rid, mode="audit",
                                enabled_tools=config.DEFAULT_ENABLED_TOOLS | {"get_solution"},
                                lambda_tokens=config.LAMBDA_X))
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/arjunsingh/LoopHole && .venv/bin/python -m pytest envs/loop_auditor_env/tests/test_scenarios.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add envs/loop_auditor_env/config.py envs/loop_auditor_env/scenarios.py envs/loop_auditor_env/tests/test_scenarios.py
git commit -m "feat(env): add scenarios layer (audit/gate + tool toggles)" -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Per-run state, metered read tools, and stateful budget/solution tools (`env.py`)

**Files:**
- Modify: `envs/loop_auditor_env/env.py` (add state + tools; register on MCP; build scenario registry; route `audit-trace` through scenarios)
- Test: `envs/loop_auditor_env/tests/test_gate_env.py` (capability + budget + toggle)

**Interfaces:**
- Consumes: `accounting.TokenMeter`, `accounting.estimate_tokens`, `scenarios.enumerate_scenarios`, `scenarios.Scenario`, `config.SOLUTION_COST`, `tools.*`.
- Produces (module-level in `env.py`): `_SCENARIOS: dict[str, Scenario]`; `_run: dict` per-run state; async tools `get_budget()`, `get_solution()`; `_begin_run(scenario)` helper; `audit_trace(scenario_id)` template.

- [ ] **Step 1: Write the failing test**

```python
# envs/loop_auditor_env/tests/test_gate_env.py
import os
import pytest

os.environ.setdefault("LOOP_AUDITOR_JUDGE_STUB", "1")
pytest.importorskip("hud")

from loop_auditor_env import env as E  # noqa: E402


async def test_capability_serves_all_ten_tools():
    from hud.capabilities.mcp import MCPClient
    await E.env.start()
    try:
        client = await MCPClient.connect(E.env.capability("trace-inspector"))
        try:
            names = sorted(t.name for t in await client.list_tools())
            assert names == sorted([
                "get_trace_summary", "get_iteration", "get_step", "search_steps",
                "get_errors", "get_step_io", "get_budget", "get_solution",
                "observe_next", "gate",
            ])
        finally:
            await client.close()
    finally:
        await E.env.stop()


async def test_get_budget_reflects_charges():
    sc = next(s for s in E._SCENARIOS.values() if s.mode == "audit")
    E._begin_run(sc)
    before = (await E.get_budget())
    await E.get_trace_summary()           # a read tool charges the meter
    after = (await E.get_budget())
    assert E._run["meter"].spent > 0
    assert "spent" in before and "spent" in after


async def test_get_solution_disabled_by_default_scenario():
    sc = next(s for s in E._SCENARIOS.values() if s.mode == "audit" and "solution" not in s.id)
    E._begin_run(sc)
    msg = await E.get_solution()
    assert "disabled" in msg.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/arjunsingh/LoopHole && .venv/bin/python -m pytest envs/loop_auditor_env/tests/test_gate_env.py -q`
Expected: FAIL — `AttributeError: module 'loop_auditor_env.env' has no attribute '_SCENARIOS'`

- [ ] **Step 3a: Extend imports + state in `env.py`** (replace the dual-import block and the `_current` line)

Replace the existing `try/except ImportError` import block with:

```python
try:  # package mode (pytest)
    from . import accounting, config, judge, scenarios, serialize
    from . import reward as reward_mod
    from . import tools as tools_mod
    from . import verdict as verdict_mod
except ImportError:  # flat mode (hud `env:env`)
    import accounting
    import config
    import judge
    import scenarios
    import serialize
    import reward as reward_mod
    import tools as tools_mod
    import verdict as verdict_mod
```

Replace `_current = {"trace_view": None}` with:

```python
# Full traces keyed by run_id (incl. planted_failure).
_TRACES = {t["run_id"]: t for t in load_fixture_traces()}
_SCENARIOS = {s.id: s for s in scenarios.enumerate_scenarios(list(_TRACES.values()))}

# Per-run state (one container per eval -> module global is safe).
_run: dict = {"scenario": None, "trace_view": None, "ground_truth": None,
              "meter": accounting.TokenMeter(), "cursor": 0, "decisions": [],
              "fault_iteration": None}


def _begin_run(scenario) -> None:
    trace = _TRACES[scenario.trace_id]
    view, gt = strip_ground_truth(trace)
    _run.update(scenario=scenario, trace_view=view, ground_truth=gt,
                meter=accounting.TokenMeter(budget=scenario.token_budget),
                cursor=0, decisions=[], fault_iteration=scenarios.fault_iteration(trace))


def _enabled(name: str) -> bool:
    sc = _run["scenario"]
    return sc is None or name in sc.enabled_tools


def _charge_output(category: str, value) -> None:
    _run["meter"].charge(accounting.estimate_tokens(value), category)
```

> Note: the old `_current["trace_view"]` is replaced by `_run["trace_view"]`. Update the existing read-tool wrappers accordingly in Step 3b.

- [ ] **Step 3b: Replace the existing read-tool wrappers** (`get_trace_summary`, `get_iteration`, `get_step`) and add the new pure-tool wrappers + budget/solution. Replace the three existing async wrappers with this block:

```python
async def get_trace_summary() -> str:
    if not _enabled("get_trace_summary"):
        return "tool disabled for this scenario"
    out = tools_mod.get_trace_summary(_run["trace_view"])
    _charge_output("tool", out)
    return out


async def get_iteration(index: int) -> str:
    if not _enabled("get_iteration"):
        return "tool disabled for this scenario"
    try:
        out = json.dumps(tools_mod.get_iteration(_run["trace_view"], index))
    except (IndexError, TypeError) as exc:
        return f"error: {exc}"
    _charge_output("tool", out)
    return out


async def get_step(step_id: str) -> str:
    if not _enabled("get_step"):
        return "tool disabled for this scenario"
    try:
        out = json.dumps(tools_mod.get_step(_run["trace_view"], step_id))
    except (KeyError, TypeError) as exc:
        return f"error: {exc}"
    _charge_output("tool", out)
    return out


async def search_steps(query: str) -> str:
    if not _enabled("search_steps"):
        return "tool disabled for this scenario"
    out = json.dumps(tools_mod.search_steps(_run["trace_view"], query))
    _charge_output("tool", out)
    return out


async def get_errors() -> str:
    if not _enabled("get_errors"):
        return "tool disabled for this scenario"
    out = json.dumps(tools_mod.get_errors(_run["trace_view"]))
    _charge_output("tool", out)
    return out


async def get_step_io(step_id: str) -> str:
    if not _enabled("get_step_io"):
        return "tool disabled for this scenario"
    try:
        out = json.dumps(tools_mod.get_step_io(_run["trace_view"], step_id))
    except (KeyError, TypeError) as exc:
        return f"error: {exc}"
    _charge_output("tool", out)
    return out


async def get_budget() -> dict:
    m = _run["meter"]
    return {"spent": m.spent, "remaining": m.remaining, "breakdown": dict(m.breakdown),
            "lambda": _run["scenario"].lambda_tokens if _run["scenario"] else 0.0}


async def get_solution() -> str:
    if not _enabled("get_solution"):
        return "tool disabled for this scenario"
    _run["meter"].charge(config.SOLUTION_COST, "solution")  # expensive on purpose
    ref = tools_mod.get_reference_solution(_run["trace_view"])
    return ref if ref else "reference unavailable"
```

- [ ] **Step 3c: Register the new tools** in `@env.initialize` (`_up`). After the existing `server.tool(...)` lines add:

```python
        server.tool(search_steps)
        server.tool(get_errors)
        server.tool(get_step_io)
        server.tool(get_budget)
        server.tool(get_solution)
        server.tool(observe_next)   # defined in Task 6
        server.tool(gate)           # defined in Task 6
```

> Task 6 adds `observe_next`/`gate`; if running Task 5 in isolation, temporarily omit those two `server.tool(...)` lines and the two names from the Task-5 capability test, then restore in Task 6. (Subagent-driven execution runs 5→6 in order, so prefer adding all seven now and completing Task 6 before re-running the capability test.)

- [ ] **Step 3d: Route `audit-trace` through scenarios.** Replace the existing `@env.template(id="audit-trace")` function with:

```python
@env.template(id="audit-trace")
async def audit_trace(scenario_id: "str | None" = None):
    if scenario_id is None:
        scenario_id = next(s for s in _SCENARIOS if s.startswith("audit__"))
    _begin_run(_SCENARIOS[scenario_id])
    prompt = build_prompt(_run["trace_view"])
    _charge_output("prompt", prompt)
    answer = yield prompt
    yield score_verdict(answer, _run["trace_view"], _run["ground_truth"])
```

> Also update `build_taskset()` and the `__main__` smoke to pass `scenario_id` instead of `run_id` (Task 7 rewrites `build_taskset`; for the smoke, use `audit_trace.func(scenario_id=next(s for s in _SCENARIOS if s.startswith("audit__")))`).

- [ ] **Step 4: Run test to verify it passes** (after Task 6's `observe_next`/`gate` exist; if running 5 standalone, see Step 3c note)

Run: `cd /Users/arjunsingh/LoopHole && .venv/bin/python -m pytest envs/loop_auditor_env/tests/test_gate_env.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add envs/loop_auditor_env/env.py envs/loop_auditor_env/tests/test_gate_env.py
git commit -m "feat(env): per-run meter, metered read tools, get_budget/get_solution, scenario-routed audit" -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: Gate task — `observe_next`, `gate`, and the `gate-trace` template (`env.py`)

**Files:**
- Modify: `envs/loop_auditor_env/env.py` (add `observe_next`, `gate`, `gate-trace` template; reward via `compute_gate_reward`)
- Test: `envs/loop_auditor_env/tests/test_gate_task.py`

**Interfaces:**
- Consumes: `_run`, `_begin_run`, `_enabled`, `_charge_output`, `_SCENARIOS`, `reward_mod.compute_gate_reward`, `accounting`.
- Produces: async `observe_next() -> str`; async `gate(decision, reason="", step_id=None, failure_type=None) -> str`; `gate_trace(scenario_id)` template; `_gate_reward() -> float`.

- [ ] **Step 1: Write the failing test**

```python
# envs/loop_auditor_env/tests/test_gate_task.py
import os
import pytest

os.environ.setdefault("LOOP_AUDITOR_JUDGE_STUB", "1")
pytest.importorskip("hud")

from loop_auditor_env import env as E  # noqa: E402


def _gate_scenario(buggy: bool):
    for s in E._SCENARIOS.values():
        if s.mode != "gate":
            continue
        is_buggy = E._TRACES[s.trace_id].get("planted_failure") is not None
        if is_buggy == buggy:
            return s
    raise AssertionError("no matching gate scenario")


async def test_observe_next_reveals_and_charges():
    E._begin_run(_gate_scenario(buggy=True))
    spent0 = E._run["meter"].spent
    out = await E.observe_next()
    assert "iteration" in out.lower() or "step_id" in out.lower()
    assert E._run["meter"].spent > spent0
    assert E._run["cursor"] == 1


async def test_gate_flag_at_fault_scores_high():
    sc = _gate_scenario(buggy=True)
    gt = E._TRACES[sc.trace_id]["planted_failure"]
    gen = E.gate_trace.func(scenario_id=sc.id)
    await gen.asend(None)                       # prompt
    # walk to the fault iteration, then flag
    for _ in range(E._run["fault_iteration"] + 1):
        await E.observe_next()
    await E.gate("flag", reason="bad route", failure_type=gt["failure_type"])
    reward = await gen.asend("done")
    assert reward >= 1.0                        # caught (1.0) + type (0.3) - small token cost


async def test_gate_clean_completed_scores_one():
    sc = _gate_scenario(buggy=False)
    gen = E.gate_trace.func(scenario_id=sc.id)
    await gen.asend(None)
    while "no more" not in (await E.observe_next()).lower():
        pass
    reward = await gen.asend("done")
    assert reward > 0.0                         # completed clean, minus tiny token cost
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/arjunsingh/LoopHole && .venv/bin/python -m pytest envs/loop_auditor_env/tests/test_gate_task.py -q`
Expected: FAIL — `AttributeError: module 'loop_auditor_env.env' has no attribute 'gate_trace'`

- [ ] **Step 3a: Add `observe_next` and `gate`** (in `env.py`, after `get_solution`)

```python
async def observe_next() -> str:
    """Reveal the next iteration in the gate replay stream; charges its tokens."""
    if not _enabled("observe_next"):
        return "tool disabled for this scenario"
    iters = _run["trace_view"].get("iterations", [])
    i = _run["cursor"]
    if i >= len(iters):
        _run["decisions"].append({"decision": "completed", "iteration": i - 1})
        return "no more iterations"
    iteration = iters[i]
    _run["cursor"] = i + 1
    tok = sum(int(s.get("tokens", 0) or 0) for s in iteration.get("steps", []))
    _run["meter"].charge(tok or accounting.estimate_tokens(iteration), "stream")
    return f"iteration {iteration.get('index', i)}: " + json.dumps(iteration)


async def gate(decision: str, reason: str = "", step_id: str = "", failure_type: str = "") -> str:
    """continue | stop | flag. stop/flag end the run; the last observed iteration is recorded."""
    if not _enabled("gate"):
        return "tool disabled for this scenario"
    if decision not in ("continue", "stop", "flag"):
        return f"error: decision must be continue|stop|flag, got {decision!r}"
    if decision == "continue":
        return "continuing"
    _run["decisions"].append({
        "decision": decision, "iteration": max(0, _run["cursor"] - 1),
        "step_id": step_id or None, "failure_type": failure_type or None,
    })
    return f"{decision} recorded"
```

- [ ] **Step 3b: Add `_gate_reward` and the `gate-trace` template** (in `env.py`, after `audit_trace`)

```python
def _gate_reward() -> float:
    decisions = _run["decisions"]
    final = next((d for d in decisions if d["decision"] in ("flag", "stop")), None)
    if final is None:  # ran to end without flag/stop
        decision, stop_iteration, flagged_type = "completed", None, None
    else:
        decision = final["decision"]
        stop_iteration = final["iteration"]
        flagged_type = final.get("failure_type")
    gt = _run["ground_truth"]
    return reward_mod.compute_gate_reward(
        decision=decision,
        stop_iteration=stop_iteration,
        fault_iteration=_run["fault_iteration"],
        tokens_spent=_run["meter"].spent,
        flagged_failure_type=flagged_type,
        planted_failure_type=(gt or {}).get("failure_type"),
        lambda_tokens=_run["scenario"].lambda_tokens,
    )


GATE_INSTRUCTIONS = (
    "You are gating a running agent loop to catch a fault early and save tokens.\n"
    "- Call observe_next() to reveal the next iteration (it costs tokens).\n"
    "- After each, call gate('continue') to keep going, or gate('flag', reason, "
    "step_id, failure_type) the moment you see the planted fault.\n"
    "- If the run is clean, keep observing until 'no more iterations', then stop.\n"
    "- Use get_budget() to track spend. Flag as early as possible once you're sure.\n"
)


@env.template(id="gate-trace")
async def gate_trace(scenario_id: "str | None" = None):
    if scenario_id is None:
        scenario_id = next(s for s in _SCENARIOS if s.startswith("gate__"))
    _begin_run(_SCENARIOS[scenario_id])
    _charge_output("prompt", GATE_INSTRUCTIONS)
    _answer = yield GATE_INSTRUCTIONS
    yield _gate_reward()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/arjunsingh/LoopHole && .venv/bin/python -m pytest envs/loop_auditor_env/tests/test_gate_task.py envs/loop_auditor_env/tests/test_gate_env.py -q`
Expected: PASS (test_gate_task 3 + test_gate_env 3)

- [ ] **Step 5: Commit**

```bash
git add envs/loop_auditor_env/env.py envs/loop_auditor_env/tests/test_gate_task.py
git commit -m "feat(env): gate-trace task with observe_next/gate + compute_gate_reward" -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: Mint scenarios into tasks + full verification (`tasks.py`, `env.py` smoke)

**Files:**
- Modify: `envs/loop_auditor_env/tasks.py` (mint one task per scenario)
- Modify: `envs/loop_auditor_env/env.py` (`build_taskset` + `__main__` smoke use scenario ids)
- Test: `envs/loop_auditor_env/tests/test_tasks.py`

**Interfaces:**
- Consumes: `env._SCENARIOS`, `env.audit_trace`, `env.gate_trace`.
- Produces: `tasks` list (one HUD task per scenario, `.slug == scenario.id`).

- [ ] **Step 1: Write the failing test**

```python
# envs/loop_auditor_env/tests/test_tasks.py
import os
import pytest

os.environ.setdefault("LOOP_AUDITOR_JUDGE_STUB", "1")
pytest.importorskip("hud")


def test_tasks_cover_audit_and_gate_per_trace():
    import importlib, sys
    sys.path.insert(0, "envs/loop_auditor_env")     # flat import like hud does
    tasks_mod = importlib.import_module("tasks")
    slugs = {t.slug for t in tasks_mod.tasks}
    assert any(s.startswith("audit__") for s in slugs)
    assert any(s.startswith("gate__") for s in slugs)
    assert len(tasks_mod.tasks) == len(tasks_mod.env_mod._SCENARIOS)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/arjunsingh/LoopHole && .venv/bin/python -m pytest envs/loop_auditor_env/tests/test_tasks.py -q`
Expected: FAIL (current `tasks.py` mints per-trace `audit_trace(run_id=...)`, not per-scenario; no `env_mod` export)

- [ ] **Step 3a: Rewrite `tasks.py`**

```python
# envs/loop_auditor_env/tasks.py
"""Tasks for the loop-auditor env — one task per scenario (audit + gate).

Run:  hud eval tasks.py claude --gateway        (single)
      hud eval tasks.py claude --gateway --group 8   (GRPO-style)
"""

import env as env_mod  # flat hud entry; re-exported for tests
from env import audit_trace, env, gate_trace  # noqa: F401

tasks = []
for _sc in env_mod._SCENARIOS.values():
    _template = audit_trace if _sc.mode == "audit" else gate_trace
    _task = _template(scenario_id=_sc.id)
    _task.slug = _sc.id
    tasks.append(_task)
```

- [ ] **Step 3b: Fix `build_taskset` + smoke in `env.py`.** Replace `build_taskset` with:

```python
def build_taskset(scenario_ids=None):
    """Mint Tasks for the given scenario ids (default: all)."""
    ids = scenario_ids or list(_SCENARIOS)
    out = []
    for sid in ids:
        sc = _SCENARIOS[sid]
        template = audit_trace if sc.mode == "audit" else gate_trace
        task = template(scenario_id=sid)
        task.slug = sid
        out.append(task)
    return out
```

And in the `__main__` smoke, replace the audit generator line with:

```python
        audit_id = next(s for s in _SCENARIOS if s.startswith("audit__"))
        gen = audit_trace.func(scenario_id=audit_id)
```

- [ ] **Step 4: Run the full suite + both keyless smokes**

Run:
```bash
cd /Users/arjunsingh/LoopHole
.venv/bin/python -m pytest -q
( cd envs/loop_auditor_env && LOOP_AUDITOR_JUDGE_STUB=1 ../../.venv/bin/python env.py )
( cd envs/loop_auditor_env && LOOP_AUDITOR_JUDGE_STUB=1 ../../.venv/bin/python -c "import tasks; print('tasks:', len(tasks.tasks))" )
```
Expected: all tests PASS (34 prior + new ~26); `env.py` prints an audit reward; tasks count == number of scenarios (2× traces).

- [ ] **Step 5: Commit**

```bash
git add envs/loop_auditor_env/tasks.py envs/loop_auditor_env/env.py envs/loop_auditor_env/tests/test_tasks.py
git commit -m "feat(env): mint audit+gate tasks per scenario; scenario-id smokes" -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Post-implementation (not tasks)
- Redeploy so the new tools/scenarios appear in HUD web: `cd envs/loop_auditor_env && hud deploy .` then `hud sync tasks loop-auditor tasks.py --yes`.
- `get_solution` returns real content once Person 1's traces include `reference_solution`.

## Self-Review

**Spec coverage:**
- 10 tools → Task 2 (4 pure) + Task 5 (get_budget/get_solution) + Task 6 (observe_next/gate); existing 3 kept. ✓
- TokenMeter / cost accounting → Task 1 + metering wired in Tasks 5/6. ✓
- Two tasks (audit X unchanged reward / gate Y) → Tasks 5 (audit routing) + 6 (gate). ✓
- compute_gate_reward (detection − λ·tokens; clean vs false-flag) → Task 3. ✓
- Scenarios + per-scenario `get_solution` toggle → Task 4 (`enabled_tools`) + enforcement in Tasks 5/6 (`_enabled`). ✓
- Config knobs (LAMBDA_TOKENS, LAMBDA_X, SOLUTION_COST, DEFAULT_ENABLED_TOOLS, GATE_TURN_LIMIT) → Tasks 3/4. ✓
- X stays standalone floor → `audit-trace` + `compute_reward` untouched logic; gate is additive. ✓
- Testing (pure tools, accounting, gate reward, env capability/toggle, gate task) → Tasks 1–7. ✓
- Dependencies (Person 1 `reference_solution`; Person 3 sidecar) → noted; `get_solution` degrades to "reference unavailable". ✓

**Placeholder scan:** No TBD/TODO; every code step has complete code. The Task-5 capability test depends on Task 6's two tools — flagged explicitly in Step 3c with the standalone workaround. ✓

**Type consistency:** `gate(decision, reason, step_id, failure_type)` strings throughout; `_run` keys (`scenario, trace_view, ground_truth, meter, cursor, decisions, fault_iteration`) consistent across Tasks 5/6/7; `compute_gate_reward` signature matches its call in `_gate_reward`; `_SCENARIOS`/`Scenario.mode` consistent in Tasks 4/5/6/7. ✓
