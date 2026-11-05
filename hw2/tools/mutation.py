"""Mutation testing (mutmut) for one phase's backend suite, in the evaluation worktree.

Run after evaluate.py has set up the worktree for the same ref. The mutmut
configuration is written into the scratch worktree only; nothing reaches the repo.

Usage (from the folder that holds tools/):
  uv run --no-project --python 3.11 tools/mutation.py --ref hw2-initial \
      --out evidence/01-initial/eval --scratch <dir> [--modules app/services/arxiv.py,...]

Add --rerun-timeouts to run only the mutants that timed out in the last run again, one
at a time, and update the results. A timeout can be an artifact of a busy machine.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
STUBS = HERE / "stubs"

# Modules with the app's own logic. claude_code.py (subprocess management), db.py,
# config.py and main.py (wiring) are left out: their mutants mostly test the
# harness, not the requirements.
DEFAULT_MODULES = [
    "app/services/arxiv.py",
    "app/services/openalex.py",
    "app/services/pdf.py",
    "app/services/fulltext.py",
    "app/services/cache.py",
    "app/services/llm.py",
    "app/routers/search.py",
    "app/routers/papers.py",
    "app/routers/assistant.py",
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", required=True)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--scratch", required=True, type=Path)
    ap.add_argument("--modules", default=",".join(DEFAULT_MODULES))
    ap.add_argument("--timeout", type=int, default=10800)
    # Serial by default: a suite whose test processes share state (a temp folder or
    # database inherited through the environment) makes parallel mutants fail for
    # reasons unrelated to the mutant, which inflates the score.
    ap.add_argument("--max-children", type=int, default=1)
    ap.add_argument("--rerun-timeouts", action="store_true")
    args = ap.parse_args()
    out = args.out.resolve()
    backend = (args.scratch.resolve() / f"wt-{args.ref}" / "backend")
    modules = [m for m in args.modules.split(",") if m]

    if not args.rerun_timeouts:
        pyproject = backend / "pyproject.toml"
        text = pyproject.read_text()
        text = re.sub(r"\n\[tool\.mutmut\][\s\S]*?(?=\n\[|\Z)", "\n", text)  # drop an earlier harness config
        extra_copy = [p for p in ("conftest.py", "tests/", "pytest.ini", "setup.cfg") if (backend / p).exists()]
        text += (
            "\n[tool.mutmut]\n"
            f"source_paths = {json.dumps(modules)}\n"
            f"also_copy = {json.dumps(['app/', *extra_copy])}\n"
            'pytest_add_cli_args = ["-p", "hw2_reload", "-p", "no:randomly", "-p", "no:cacheprovider", "-q"]\n'
        )
        pyproject.write_text(text)
        subprocess.run(["rm", "-rf", "mutants"], cwd=backend, check=True)

    env = dict(os.environ)
    env["PATH"] = f"{STUBS}:{env.get('PATH', '')}"
    env["HW2_LLM_STUB_LOG"] = str(out / "llm-stub-calls-mutation.log")
    # The hw2_reload plugin lets one process run several pytest sessions (see its docstring).
    env["PYTHONPATH"] = f"{HERE / 'mutmut_support'}:{env.get('PYTHONPATH', '')}"
    for name in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "DATA_DIR", "VIRTUAL_ENV"):
        env.pop(name, None)
    env.update(CI="1", NO_COLOR="1", PYTHONDONTWRITEBYTECODE="1")
    # mutmut forks a child per mutant. On macOS, a forked child that asks the OS
    # for proxy settings (urllib's getproxies, used when an httpx client is built)
    # can crash with SIGSEGV; any *_proxy variable makes Python skip that lookup.
    # Tests fake all HTTP, so this changes nothing else.
    env.update(no_proxy="*", NO_PROXY="*")
    # Pinned to the versions the HW2 evaluation used.
    uv = ["uv", "run", "--no-sync", "--with", "mutmut==3.8.1", "--with", "pytest-timeout==2.4.0"]

    def current_statuses() -> dict[str, str]:
        res = subprocess.run([*uv, "mutmut", "results", "--all", "true"], cwd=backend, env=env,
                             capture_output=True, text=True)
        found: dict[str, str] = {}
        for line in res.stdout.splitlines():
            m = re.match(r"\s*(app\.[\w.]+__mutmut_\d+):\s*(.+)$", line)
            if m:
                found[m.group(1)] = m.group(2).strip()
        return found

    def mutmut_run(log_name: str, *mutants: str) -> tuple[int | None, int]:
        log = out / "logs" / log_name
        log.parent.mkdir(parents=True, exist_ok=True)
        start = time.monotonic()
        with log.open("w") as fh:
            try:
                rc = subprocess.run([*uv, "mutmut", "run", "--max-children", str(args.max_children), *mutants], cwd=backend,
                                    env=env, stdout=fh, stderr=subprocess.STDOUT, timeout=args.timeout).returncode
            except subprocess.TimeoutExpired:
                rc = None
        return rc, round(time.monotonic() - start)

    rerun = None
    if args.rerun_timeouts:
        previous = json.loads((out / "mutation.json").read_text())
        (out / "mutation-before-rerun.json").write_text(json.dumps(previous, indent=2) + "\n")
        rc, seconds = previous["rc"], previous["seconds"]
        timed_out = sorted(m for m, s in current_statuses().items() if s == "timeout")
        rerun_rc, rerun_seconds = mutmut_run("mutmut-rerun-timeouts.log", *timed_out)
        statuses = current_statuses()
        rerun = {"rc": rerun_rc, "seconds": rerun_seconds, "after": {m: statuses.get(m) for m in timed_out}}
    else:
        rc, seconds = mutmut_run("mutmut-run.log")
        statuses = current_statuses()

    def module_of(mutant: str) -> str:
        return mutant.split(".x_")[0] if ".x_" in mutant else mutant.rsplit(".", 1)[0]

    by_module: dict[str, Counter] = {}
    for mutant, status in statuses.items():
        by_module.setdefault(module_of(mutant), Counter())[status] += 1
    total = Counter(statuses.values())
    killed = total.get("killed", 0)
    covered = killed + total.get("survived", 0) + total.get("timeout", 0)
    survivors = sorted(m for m, s in statuses.items() if s == "survived")

    # Keep the diff of every survivor: it is the evidence, and round 2's feedback.
    diffs = []
    for mutant in survivors:
        show = subprocess.run([*uv, "mutmut", "show", mutant], cwd=backend, env=env, capture_output=True, text=True)
        diff = "\n".join(l for l in show.stdout.splitlines() if not l.startswith("#"))
        diffs.append(f"## {mutant}\n\n```diff\n{diff.strip()}\n```\n")
    (out / "mutation-survivors.md").write_text(f"# Surviving mutants ({len(survivors)})\n\n" + "\n".join(diffs))

    result = {
        "rc": rc, "seconds": seconds, "modules": modules, "max_children": args.max_children,
        "counts": dict(total),
        "mutants": len(statuses),
        "killed": killed,
        "score_all": round(100 * killed / len(statuses), 1) if statuses else None,
        "score_covered": round(100 * killed / covered, 1) if covered else None,
        "by_module": {k: dict(v) for k, v in sorted(by_module.items())},
        "survivors": survivors,
        "timeouts_rerun": rerun,
    }
    (out / "mutation.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: result[k] for k in ("rc", "seconds", "mutants", "killed", "score_all", "score_covered", "counts")}, indent=2))


if __name__ == "__main__":
    main()
