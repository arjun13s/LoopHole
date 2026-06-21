"""MCP server wrapper for the Loop-Auditor self-improvement analyzer."""

from __future__ import annotations

from . import analyzer


def classify_run(eval_result: dict, sidecar: dict) -> "dict | None":
    """Classify one joined eval_result/verdict_sidecar pair."""
    return analyzer.classify(eval_result, sidecar)


def analyze_files(
    results_path: str,
    verdicts_path: str,
    out_path: str = "improvement_records.jsonl",
) -> dict:
    """Analyze JSONL files and write improvement_records.jsonl."""
    eval_results = analyzer.read_jsonl(results_path)
    sidecars = analyzer.sidecar_index(analyzer.read_jsonl(verdicts_path))
    records = analyzer.analyze(eval_results, sidecars)
    analyzer.write_jsonl(records, out_path)
    return {"out_path": out_path, **analyzer.summarize(records)}


def markdown_report(results_path: str, verdicts_path: str) -> str:
    """Return a markdown self-improvement report for JSONL inputs."""
    eval_results = analyzer.read_jsonl(results_path)
    sidecars = analyzer.sidecar_index(analyzer.read_jsonl(verdicts_path))
    return analyzer.format_markdown_summary(analyzer.analyze(eval_results, sidecars))


def build_server():
    from fastmcp import FastMCP

    server = FastMCP(name="loop-auditor-self-improve")
    server.tool(classify_run)
    server.tool(analyze_files)
    server.tool(markdown_report)
    return server


def main() -> None:
    build_server().run(transport="stdio", show_banner=False)


if __name__ == "__main__":
    main()
