"""Dataclasses for trace.jsonl rows and deterministic labels."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


FailureType = Literal["resource_misuse", "tool_misuse", "routing", "wrong_file_edit"]
FixAction = Literal["insert", "remove", "replace"]


@dataclass(frozen=True)
class ToolResult:
    status: Literal["ok", "error", "timeout"]
    exit_code: int | None = None
    stdout_ref: str | None = None
    stderr_ref: str | None = None
    summary: str = ""

    def to_json(self) -> dict[str, Any]:
        return {key: value for key, value in asdict(self).items() if value is not None}


@dataclass(frozen=True)
class ActionSpan:
    step_id: str
    tool_name: str
    args: dict[str, Any]
    result: ToolResult
    summary: str
    tokens: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        out = asdict(self)
        out["result"] = self.result.to_json()
        if not out["metadata"]:
            del out["metadata"]
        return out


@dataclass(frozen=True)
class StructuredFix:
    action: FixAction
    step_id: str
    tool_name: str | None = None
    target: str | None = None

    def to_json(self) -> dict[str, Any]:
        return {key: value for key, value in asdict(self).items() if value is not None}


@dataclass(frozen=True)
class GroundTruth:
    case_id: str
    fault_present: bool
    fault_step_id: str | None
    failure_type: FailureType | None
    fix: StructuredFix | None

    def to_json(self) -> dict[str, Any]:
        out = asdict(self)
        if self.fix is not None:
            out["fix"] = self.fix.to_json()
        return out
