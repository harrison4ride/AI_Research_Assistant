"""Compare evaluation results across phases (Markdown tables + JSON for charts).

Usage (from the folder that holds tools/):
  python3 tools/compare.py initial=evidence/01-initial/eval round1=evidence/02-round1/eval ... \
      > evidence/final/comparison.md
"""

import json
import sys
from pathlib import Path


def load(path: Path) -> dict:
    m = json.loads((path / "metrics.json").read_text())
    mfile = path / "mutation.json"
    m["mutation"] = json.loads(mfile.read_text()) if mfile.is_file() else None
    return m


def cell(value, fmt="{}"):
    return "–" if value is None else fmt.format(value)


def main() -> None:
    phases = []
    for arg in sys.argv[1:]:
        name, path = arg.split("=", 1)
        phases.append((name, load(Path(path))))
    names = [n for n, _ in phases]
    out = []

    def table(title, rows):
        out.append(f"### {title}\n")
        out.append("| Measure | " + " | ".join(names) + " |")
        out.append("|---|" + "---|" * len(names))
        for label, fn in rows:
            out.append(f"| {label} | " + " | ".join(fn(m) for _, m in phases) + " |")
        out.append("")

    def counts(layer, key):
        return lambda m: cell((m.get(layer) or {}).get("counts", {}).get(key))

    table("Execution (clean checkout)", [
        ("Backend tests", counts("backend", "total")),
        ("Backend passed", counts("backend", "passed")),
        ("Backend failed", counts("backend", "failed")),
        ("Backend xfail (known app bugs)", counts("backend", "xfail")),
        ("Frontend tests", counts("frontend", "total")),
        ("Frontend passed", counts("frontend", "passed")),
        ("Frontend failed", counts("frontend", "failed")),
        ("End-to-end tests", lambda m: cell((m.get("e2e") or {}).get("tests"))),
        ("End-to-end runs passing all", lambda m: cell(
            None if not m.get("e2e") else
            f"{sum(1 for r in m['e2e']['runs'] if r['failed'] == 0)}/{len(m['e2e']['runs'])}")),
        ("Backend time (s)", lambda m: cell((m.get("backend") or {}).get("run", {}).get("seconds"))),
        ("Frontend time (s)", lambda m: cell((m.get("frontend") or {}).get("run", {}).get("seconds"))),
    ])

    def cov(layer, key):
        return lambda m: cell(((m.get(layer) or {}).get("coverage") or {}).get(key), "{}%")

    table("Coverage", [
        ("Backend line", cov("backend", "line_pct")),
        ("Backend branch", cov("backend", "branch_pct")),
        ("Frontend line", cov("frontend", "line_pct")),
        ("Frontend branch", cov("frontend", "branch_pct")),
    ])

    table("Stability and isolation", [
        ("Unstable unit tests (5 shuffled runs)", lambda m: cell(
            None if "flaky" not in m else len(m["flaky"].get("backend", [])) + len(m["flaky"].get("frontend", [])))),
        ("Backend tests failing without network", lambda m: cell(
            None if "hermetic" not in m else len(m["hermetic"]["fail_only_without_network"]))),
        ("Calls to the claude stub", lambda m: cell((m.get("backend") or {}).get("llm_stub_calls"))),
    ])

    table("Mutation testing", [
        ("Mutation score (killed / all)", lambda m: cell((m["mutation"] or {}).get("score_all"), "{}%")),
        ("Surviving mutants", lambda m: cell((m["mutation"] or {}).get("counts", {}).get("survived"))),
    ])

    table("Assertions", [
        ("Backend test functions", lambda m: cell((m.get("static") or {}).get("backend", {}).get("test_functions"))),
        ("Backend assertions per test", lambda m: cell((m.get("static") or {}).get("backend", {}).get("mean_assertions"))),
        ("Backend status-code-only tests", lambda m: cell(len((m.get("static") or {}).get("backend", {}).get("status_code_only", [])))),
        ("Frontend test blocks", lambda m: cell((m.get("static") or {}).get("frontend", {}).get("test_blocks"))),
        ("Frontend expect() per test", lambda m: cell((m.get("static") or {}).get("frontend", {}).get("mean_assertions"))),
    ])

    # Mutation score per module.
    mods = sorted({mod for _, m in phases if m["mutation"] for mod in m["mutation"]["by_module"]})
    if mods:
        out.append("### Mutation score per module (killed / all mutants)\n")
        out.append("| Module | " + " | ".join(names) + " |")
        out.append("|---|" + "---|" * len(names))
        for mod in mods:
            row = []
            for _, m in phases:
                c = (m["mutation"] or {}).get("by_module", {}).get(mod)
                row.append("–" if not c else f"{100 * c.get('killed', 0) / sum(c.values()):.1f}%")
            out.append(f"| {mod.replace('app.', '')} | " + " | ".join(row) + " |")
        out.append("")

    print("\n".join(out))
    chart = {name: {
        "backend_line": ((m.get("backend") or {}).get("coverage") or {}).get("line_pct"),
        "backend_branch": ((m.get("backend") or {}).get("coverage") or {}).get("branch_pct"),
        "frontend_line": ((m.get("frontend") or {}).get("coverage") or {}).get("line_pct"),
        "frontend_branch": ((m.get("frontend") or {}).get("coverage") or {}).get("branch_pct"),
        "mutation": (m["mutation"] or {}).get("score_all"),
    } for name, m in phases}
    Path("evidence/final").mkdir(parents=True, exist_ok=True)
    Path("evidence/final/chart-data.json").write_text(json.dumps(chart, indent=2) + "\n")


if __name__ == "__main__":
    main()
