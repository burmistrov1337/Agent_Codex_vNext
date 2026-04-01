from __future__ import annotations

from dataclasses import asdict

from ..contracts import RunEnvelope


def build_n8n_payload(envelope: RunEnvelope) -> dict:
    return {
        "run_id": envelope.run_id,
        "request": envelope.request,
        "mode": envelope.mode,
        "final_summary": envelope.final_summary,
        "alerts": envelope.alerts,
        "artifacts": [asdict(artifact) for artifact in envelope.artifacts],
        "results": [asdict(result) for result in envelope.results],
    }
