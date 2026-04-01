from __future__ import annotations

from dataclasses import asdict
import json

from ..config import Settings
from ..contracts import HookEvent, RunEnvelope
from .policy import PolicyDecision, evaluate_tool_action


class HookPipeline:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.audit_log_path = settings.runtime_root / "audit" / "hook_events.jsonl"

    def pre_task(self, request: str, mode: str) -> HookEvent:
        event = HookEvent(
            phase="pre_task",
            subject=mode,
            decision="allow",
            explanation=f"Запрос принят в режим {mode}: {request[:140]}",
            risk="low",
        )
        self._write_event(event)
        return event

    def pre_tool(self, tool_name: str, target_path: str | None = None) -> PolicyDecision:
        decision = evaluate_tool_action(
            tool_name,
            target_path=target_path,
            scratchpad_root=str(self.settings.runtime_root / "scratchpad"),
        )
        self._write_event(
            HookEvent(
                phase="pre_tool",
                subject=tool_name,
                decision="allow" if decision.allowed else "deny",
                explanation=decision.explanation,
                risk=decision.risk,
            )
        )
        return decision

    def post_tool(self, tool_name: str, details: str) -> HookEvent:
        event = HookEvent(
            phase="post_tool",
            subject=tool_name,
            decision="recorded",
            explanation=details[:240],
            risk="low",
        )
        self._write_event(event)
        return event

    def pre_reply(self, final_summary: str) -> HookEvent:
        status = "allow"
        risk = "low"
        if "based on findings" in final_summary.lower():
            status = "warn"
            risk = "medium"
        event = HookEvent(
            phase="pre_reply",
            subject="final_reply",
            decision=status,
            explanation=final_summary[:240],
            risk=risk,
        )
        self._write_event(event)
        return event

    def post_run(self, envelope: RunEnvelope) -> HookEvent:
        event = HookEvent(
            phase="post_run",
            subject=envelope.run_id,
            decision="recorded",
            explanation=envelope.final_summary[:240],
            risk="low",
        )
        self._write_event(event)
        return event

    def _write_event(self, event: HookEvent) -> None:
        self.audit_log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.audit_log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(event), ensure_ascii=False) + "\n")
