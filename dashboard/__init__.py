"""Loop-Auditor dashboard (Person 3).

Standalone, read-only consumer of the frozen contracts:
  - schemas/eval_result.json  -> per-trace/per-model correctness + token records
  - schemas/verdict.json      -> optional sidecar for verdict drill-down
  - schemas/trace.json        -> trace replay with the planted-failure step highlighted

No dependency on loop_auditor_env (decoupled by design). Rich static-render is the
primary surface (visible inside any CLI agent); Textual interactive is a stretch layer.
"""

__all__ = ["model", "loader", "render"]
