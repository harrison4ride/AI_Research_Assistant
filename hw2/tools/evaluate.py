"""HW2 evaluation harness: measure one phase's test suite in a clean checkout.

Every phase is measured the same way, the way a grader would meet it: a fresh
git worktree at the phase's tag (no .env, no local data), dependencies installed
from the lock files, and the `claude` CLI replaced by a stub that fails and logs,
so no test can spend real LLM usage.

Steps (--steps, comma-separated; default all):
  setup     worktree + `uv sync --locked` + `npm ci`
  backend   pytest with branch coverage (coverage.py), JUnit XML
  frontend  vitest with v8 coverage, JUnit XML
  flaky     N extra runs per suite in random order; tests whose outcome changes
  parallel  pytest with 8 worker processes (pytest-xdist): is the suite process-safe?
  hermetic  pytest with sockets disabled except localhost (pytest-socket)
  faults    held-out seeded faults (tools/faults/*.patch): which tests detect each
  static    tests and assertions per test (AST for Python, a scanner for TS)
  e2e       the Playwright suite, run --e2e-runs times in full (browser installed first)

Usage (from the folder that holds tools/):
  uv run --no-project --python 3.11 tools/evaluate.py --ref hw2-initial \
      --out evidence/01-initial/eval --scratch <dir>

The app's repository is HW2_REPO if set, else the git work tree around tools/ (hw2/ in
the repository), else the sibling folder AI_Research_Assistant (the original layout).
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent


def find_repo() -> Path:
    if os.environ.get("HW2_REPO"):
        return Path(os.environ["HW2_REPO"]).resolve()
    top = subprocess.run(["git", "-C", str(HERE), "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    if top.returncode == 0:
        return Path(top.stdout.strip())
    sibling = HERE.parent.parent / "AI_Research_Assistant"
    if sibling.is_dir():
        return sibling
    sys.exit("Cannot find the app's repository: set HW2_REPO to its path.")


REPO = find_repo()
FAULTS = HERE / "faults"
STUBS = HERE / "stubs"
ALL_STEPS = ["setup", "backend", "frontend", "flaky", "parallel", "hermetic", "faults", "static", "e2e"]

# Test-only tools the harness adds when the suite does not declare them itself.
# Pinned to the versions the HW2 evaluation used.
PY_EVAL_TOOLS = ["pytest-cov==7.1.0", "pytest-timeout==2.4.0", "pytest-randomly==5.0.0", "pytest-socket==0.8.1",
                 "pytest-xdist==3.8.0"]


# ----------------------------------------------------------------------------- helpers


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def run(cmd: list[str], cwd: Path, env: dict[str, str], logfile: Path, timeout: float) -> dict:
    """Run a command, write its output to `logfile`, return rc, seconds, timed_out."""
    logfile.parent.mkdir(parents=True, exist_ok=True)
    start = time.monotonic()
    with logfile.open("w") as fh:
        fh.write(f"$ (cd {cwd} && {' '.join(cmd)})\n\n")
        fh.flush()
        try:
            proc = subprocess.run(cmd, cwd=cwd, env=env, stdout=fh, stderr=subprocess.STDOUT,
                                  timeout=timeout, start_new_session=True)
            rc, timed_out = proc.returncode, False
        except subprocess.TimeoutExpired:
            rc, timed_out = None, True
            fh.write(f"\n[harness] TIMEOUT after {timeout:.0f}s\n")
    return {"rc": rc, "seconds": round(time.monotonic() - start, 1), "timed_out": timed_out}


def port_in_use(port: int) -> bool:
    """Whether something listens on the port, on IPv4 or IPv6 localhost (no lsof needed)."""
    import socket
    for family, host in ((socket.AF_INET, "127.0.0.1"), (socket.AF_INET6, "::1")):
        try:
            with socket.socket(family, socket.SOCK_STREAM) as s:
                s.settimeout(1)
                if s.connect_ex((host, port)) == 0:
                    return True
        except OSError:
            continue
    return False


def git(*args: str, cwd: Path = REPO) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def eval_env(out: Path) -> dict[str, str]:
    env = dict(os.environ)
    # The stub directory comes first on PATH, so the app's `shutil.which("claude")`
    # finds the stub instead of the real Claude Code CLI.
    env["PATH"] = f"{STUBS}:{env.get('PATH', '')}"
    env["HW2_LLM_STUB_LOG"] = str(out / "llm-stub-calls.log")
    for name in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "DATA_DIR", "VIRTUAL_ENV"):
        env.pop(name, None)
    env.update(CI="1", NO_COLOR="1", FORCE_COLOR="0", PYTHONDONTWRITEBYTECODE="1")
    return env


def junit_outcomes(path: Path) -> dict[str, dict]:
    """{test id: {"outcome": passed|failed|skipped|xfail, "message": str}} from JUnit XML."""
    results: dict[str, dict] = {}
    if not path.is_file():
        return results
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError:
        return results
    for tc in root.iter("testcase"):
        base = f"{tc.get('classname', '')}::{tc.get('name', '')}"
        tid, n = base, 1
        while tid in results:  # duplicate names (e.g. repeated vitest titles)
            n += 1
            tid = f"{base}#{n}"
        failure = tc.find("failure")
        error = tc.find("error")
        skipped = tc.find("skipped")
        if failure is not None or error is not None:
            node = failure if failure is not None else error
            outcome, message = "failed", (node.get("message") or (node.text or ""))[:300]
        elif skipped is not None:
            text = f"{skipped.get('type', '')} {skipped.get('message', '')}"
            outcome = "xfail" if "xfail" in text.lower() else "skipped"
            message = (skipped.get("message") or "")[:300]
        else:
            outcome, message = "passed", ""
        results[tid] = {"outcome": outcome, "message": message, "time": float(tc.get("time") or 0)}
    return results


def counts(outcomes: dict[str, dict]) -> dict[str, int]:
    c = {"total": len(outcomes), "passed": 0, "failed": 0, "skipped": 0, "xfail": 0}
    for o in outcomes.values():
        c[o["outcome"]] += 1
    return c


# ----------------------------------------------------------------------------- setup


class Phase:
    def __init__(self, ref: str, out: Path, scratch: Path):
        self.ref = ref
        self.out = out
        self.commit = git("rev-parse", f"{ref}^{{commit}}")  # an annotated tag resolves to its commit
        self.wt = scratch / f"wt-{ref}"
        self.env = eval_env(out)
        self.metrics: dict = {"ref": ref, "commit": self.commit, "notes": []}
        mfile = out / "metrics.json"
        if mfile.is_file():  # keep results of steps that are not re-run
            self.metrics.update(json.loads(mfile.read_text()))
            self.metrics["ref"], self.metrics["commit"] = ref, self.commit

    @property
    def backend(self) -> Path:
        return self.wt / "backend"

    @property
    def frontend(self) -> Path:
        return self.wt / "frontend"

    def note(self, text: str) -> None:
        if text not in self.metrics["notes"]:
            self.metrics["notes"].append(text)
        log(f"NOTE: {text}")

    def save(self) -> None:
        (self.out / "metrics.json").write_text(json.dumps(self.metrics, indent=2, sort_keys=True) + "\n")

    # A suite counts as present when its test files exist in the checkout.
    def backend_tests(self) -> list[Path]:
        root = self.backend
        return sorted(p for p in root.rglob("test_*.py") if ".venv" not in p.parts and "node_modules" not in p.parts) + \
            sorted(p for p in root.rglob("*_test.py") if ".venv" not in p.parts)

    def frontend_tests(self) -> list[Path]:
        root = self.frontend
        pats = ("*.test.ts", "*.test.tsx", "*.spec.ts", "*.spec.tsx")
        files = {p for pat in pats for p in root.rglob(pat) if "node_modules" not in p.parts}
        # Playwright specs are end-to-end tests, not Vitest tests.
        return sorted(p for p in files if "e2e" not in p.parts)

    def setup(self) -> None:
        if self.wt.exists():
            head = git("rev-parse", "HEAD", cwd=self.wt)
            if head != self.commit:
                git("worktree", "remove", "--force", str(self.wt))
        if not self.wt.exists():
            git("worktree", "add", "--detach", str(self.wt), self.ref)
        log(f"worktree {self.wt} at {self.commit[:7]}")
        logs = self.out / "logs"
        r = run(["uv", "sync", "--locked", "--all-groups"], self.backend, self.env, logs / "setup-uv.log", 900)
        if r["rc"] != 0:
            self.note("`uv sync --locked` failed in a clean checkout (lock file out of date or broken); retried without --locked")
            r = run(["uv", "sync", "--all-groups"], self.backend, self.env, logs / "setup-uv-unlocked.log", 900)
        self.metrics["setup_backend"] = r
        r = run(["npm", "ci", "--no-audit", "--no-fund"], self.frontend, self.env, logs / "setup-npm.log", 900)
        if r["rc"] != 0:
            self.note("`npm ci` failed in a clean checkout (package.json and lock file out of sync); retried with npm install")
            r = run(["npm", "install", "--no-audit", "--no-fund"], self.frontend, self.env, logs / "setup-npm-install.log", 900)
        self.metrics["setup_frontend"] = r
        self.save()

    # ------------------------------------------------------------------------- backend

    def pytest_cmd(self, *extra: str, cov: bool = False, randomly: bool = False, socket: bool = False) -> list[str]:
        withs: list[str] = []
        for tool in PY_EVAL_TOOLS:
            withs += ["--with", tool]
        cmd = ["uv", "run", "--no-sync", *withs, "pytest", "-q", "-o", "console_output_style=classic",
               "--timeout=120", "-p", "no:cacheprovider"]
        # pytest-randomly is installed for every run so the plugin set stays the
        # same; it loads itself and is switched off except in the shuffled runs.
        if not randomly:
            cmd += ["-p", "no:randomly"]
        if not socket:
            cmd += ["-p", "no:socket"]
        if cov:
            cmd += ["--cov=app", "--cov-branch", f"--cov-report=json:{self.out / 'backend-coverage.json'}",
                    "--cov-report=term-missing:skip-covered"]
        return cmd + list(extra)

    def run_backend(self, name: str, *extra: str, cov=False, randomly=False, socket=False, timeout=1800) -> tuple[dict, dict]:
        junit = self.out / "junit" / f"{name}.xml"
        junit.parent.mkdir(parents=True, exist_ok=True)
        cmd = self.pytest_cmd(f"--junitxml={junit}", *extra, cov=cov, randomly=randomly, socket=socket)
        r = run(cmd, self.backend, self.env, self.out / "logs" / f"{name}.log", timeout)
        return r, junit_outcomes(junit)

    def backend_main(self) -> None:
        if not self.backend_tests():
            self.metrics["backend"] = {"present": False}
            self.note("no backend test files found")
            return
        stub_log = self.out / "llm-stub-calls.log"
        stub_log.unlink(missing_ok=True)
        data_db = self.backend / "data" / "app.db"
        existed = data_db.exists()
        r, outcomes = self.run_backend("backend", cov=True)
        cov = json.loads((self.out / "backend-coverage.json").read_text()) if (self.out / "backend-coverage.json").is_file() else None
        self.metrics["backend"] = {
            "present": True,
            "run": r,
            "counts": counts(outcomes),
            "failed": {k: v["message"] for k, v in outcomes.items() if v["outcome"] == "failed"},
            "xfail": {k: v["message"] for k, v in outcomes.items() if v["outcome"] == "xfail"},
            "coverage": coverage_py_summary(cov) if cov else None,
            "llm_stub_calls": stub_log.read_text().count("\n") if stub_log.is_file() else 0,
            "wrote_default_data_dir": (not existed) and data_db.exists(),
        }
        if self.metrics["backend"]["wrote_default_data_dir"]:
            self.note("backend tests created backend/data/app.db: the default data directory is not isolated from tests")
        if self.metrics["backend"]["llm_stub_calls"]:
            self.note(f"backend tests invoked the `claude` CLI {self.metrics['backend']['llm_stub_calls']} time(s) (would be real LLM calls on a normal machine)")
        self.save()

    # ------------------------------------------------------------------------ frontend

    def ensure_vitest_coverage(self) -> None:
        pkg = json.loads((self.frontend / "package.json").read_text())
        deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
        if "@vitest/coverage-v8" in deps:
            return
        version = json.loads((self.frontend / "node_modules" / "vitest" / "package.json").read_text())["version"]
        self.note(f"suite does not declare @vitest/coverage-v8; harness installed {version} for measurement only")
        run(["npm", "install", "--no-save", "--no-audit", "--no-fund", f"@vitest/coverage-v8@{version}"],
            self.frontend, self.env, self.out / "logs" / "setup-coverage-v8.log", 600)

    def vitest_cmd(self, junit: Path, *extra: str, cov: bool = False) -> list[str]:
        cmd = ["npx", "vitest", "run", "--reporter=default", "--reporter=junit", f"--outputFile.junit={junit}"]
        if cov:
            cmd += ["--coverage.enabled=true", "--coverage.provider=v8",
                    "--coverage.reporter=json-summary", "--coverage.reporter=json", "--coverage.reporter=text",
                    f"--coverage.reportsDirectory={self.out / 'frontend-coverage'}",
                    "--coverage.include=src/**/*.{ts,tsx}",
                    "--coverage.exclude=src/**/*.test.*", "--coverage.exclude=src/**/*.spec.*",
                    "--coverage.exclude=src/**/*.d.ts", "--coverage.exclude=src/test/**",
                    "--coverage.exclude=src/setupTests.*"]
        return cmd + list(extra)

    def run_frontend(self, name: str, *extra: str, cov=False, timeout=1200) -> tuple[dict, dict]:
        junit = self.out / "junit" / f"{name}.xml"
        junit.parent.mkdir(parents=True, exist_ok=True)
        junit.unlink(missing_ok=True)
        r = run(self.vitest_cmd(junit, *extra, cov=cov), self.frontend, self.env, self.out / "logs" / f"{name}.log", timeout)
        return r, junit_outcomes(junit)

    def frontend_main(self) -> None:
        if not self.frontend_tests():
            self.metrics["frontend"] = {"present": False}
            self.note("no frontend (Vitest) test files found")
            return
        self.ensure_vitest_coverage()
        r, outcomes = self.run_frontend("frontend", cov=True)
        summary_file = self.out / "frontend-coverage" / "coverage-summary.json"
        cov = json.loads(summary_file.read_text()) if summary_file.is_file() else None
        self.metrics["frontend"] = {
            "present": True,
            "run": r,
            "counts": counts(outcomes),
            "failed": {k: v["message"] for k, v in outcomes.items() if v["outcome"] == "failed"},
            "coverage": istanbul_summary(cov, self.frontend) if cov else None,
        }
        self.save()

    # --------------------------------------------------------------------------- flaky

    def flaky(self, runs: int) -> None:
        result = {}
        if self.backend_tests():
            seen: dict[str, set[str]] = {}
            for i in range(1, runs + 1):
                _, outcomes = self.run_backend(f"backend-shuffle-{i}", f"--randomly-seed={1000 + i}", randomly=True)
                for tid, o in outcomes.items():
                    seen.setdefault(tid, set()).add(o["outcome"])
            base = junit_outcomes(self.out / "junit" / "backend.xml")
            for tid, o in base.items():
                seen.setdefault(tid, set()).add(o["outcome"])
            result["backend"] = sorted(t for t, s in seen.items() if len(s) > 1)
        if self.frontend_tests():
            seen = {}
            for i in range(1, runs + 1):
                _, outcomes = self.run_frontend(f"frontend-shuffle-{i}", "--sequence.shuffle", f"--sequence.seed={1000 + i}")
                for tid, o in outcomes.items():
                    seen.setdefault(tid, set()).add(o["outcome"])
            base = junit_outcomes(self.out / "junit" / "frontend.xml")
            for tid, o in base.items():
                seen.setdefault(tid, set()).add(o["outcome"])
            result["frontend"] = sorted(t for t, s in seen.items() if len(s) > 1)
        result["runs_per_suite"] = runs
        self.metrics["flaky"] = result
        self.save()

    # ------------------------------------------------------------------------ parallel

    def parallel(self) -> None:
        if not self.backend_tests():
            return
        r, outcomes = self.run_backend("backend-parallel-8", "-n", "8")
        c = counts(outcomes)
        self.metrics["parallel"] = {"workers": 8, "passed": c["passed"], "failed": c["failed"],
                                    "xfailed": c["xfail"], "safe": c["failed"] == 0,  # JUnit errors count as failed
                                    "log": "logs/backend-parallel-8.log"}
        self.save()

    # ------------------------------------------------------------------------ hermetic

    def hermetic(self) -> None:
        if not self.backend_tests():
            return
        r, outcomes = self.run_backend(
            "backend-nosocket", "--disable-socket", "--allow-unix-socket",
            "--allow-hosts=127.0.0.1,localhost,::1", socket=True)
        base = junit_outcomes(self.out / "junit" / "backend.xml")
        network = sorted(t for t, o in outcomes.items()
                         if o["outcome"] == "failed" and base.get(t, {}).get("outcome") == "passed")
        self.metrics["hermetic"] = {"run": r, "fail_only_without_network": network}
        self.save()

    # -------------------------------------------------------------------------- faults

    def faults(self) -> None:
        manifest = json.loads((FAULTS / "manifest.json").read_text())
        base = {
            "backend": junit_outcomes(self.out / "junit" / "backend.xml"),
            "frontend": junit_outcomes(self.out / "junit" / "frontend.xml"),
        }
        flaky = self.metrics.get("flaky", {})
        base_secs = {
            "backend": (self.metrics.get("backend", {}).get("run") or {}).get("seconds") or 60,
            "frontend": (self.metrics.get("frontend", {}).get("run") or {}).get("seconds") or 60,
        }
        results = {}
        for fault in manifest:
            fid, layer = fault["id"], fault["layer"]
            present = self.backend_tests() if layer == "backend" else self.frontend_tests()
            if not present:
                results[fid] = {"detected": False, "detected_by": [], "note": "no tests for this layer"}
                continue
            patch = FAULTS / f"{fid}.patch"
            subprocess.run(["git", "apply", str(patch)], cwd=self.wt, check=True)
            try:
                timeout = max(300, 6 * base_secs[layer])
                if layer == "backend":
                    r, outcomes = self.run_backend(f"fault-{fid}", timeout=timeout)
                else:
                    r, outcomes = self.run_frontend(f"fault-{fid}", timeout=timeout)
            finally:
                subprocess.run(["git", "apply", "-R", str(patch)], cwd=self.wt, check=True)
            unstable = set(flaky.get(layer, []))
            detected_by = sorted(
                t for t, o in outcomes.items()
                if o["outcome"] == "failed" and base[layer].get(t, {}).get("outcome") == "passed" and t not in unstable
            )
            hang = r["timed_out"]
            results[fid] = {
                "detected": bool(detected_by) or hang,
                "detected_by": detected_by,
                "timed_out": hang,
                "seconds": r["seconds"],
            }
            log(f"fault {fid}: {'DETECTED' if results[fid]['detected'] else 'missed'} ({len(detected_by)} tests)")
        hist = [f["id"] for f in manifest if f["origin"].startswith("history")]
        self.metrics["faults"] = {
            "results": results,
            "detected": sum(r["detected"] for r in results.values()),
            "total": len(results),
            "detected_history": sum(results[i]["detected"] for i in hist),
            "total_history": len(hist),
            "detected_backend": sum(r["detected"] for k, r in results.items() if k.startswith("B")),
            "total_backend": sum(1 for k in results if k.startswith("B")),
            "detected_frontend": sum(r["detected"] for k, r in results.items() if k.startswith("F")),
            "total_frontend": sum(1 for k in results if k.startswith("F")),
        }
        self.save()

    # ----------------------------------------------------------------------------- e2e

    def e2e(self, runs: int) -> None:
        pkg = json.loads((self.frontend / "package.json").read_text())
        if "test:e2e" not in pkg.get("scripts", {}):
            self.note("no test:e2e script; end-to-end step skipped")
            return
        port = int(self.env.get("E2E_PORT", "8765"))
        if port_in_use(port):
            self.note(f"port {port} is in use; end-to-end step skipped")
            return
        logs = self.out / "logs"
        if "test:e2e:install" in pkg["scripts"]:
            run(["npm", "run", "test:e2e:install"], self.frontend, self.env, logs / "e2e-install.log", 900)
        results = []
        for i in range(1, runs + 1):
            junit = self.out / "junit" / f"e2e-{i}.xml"
            env = dict(self.env, PLAYWRIGHT_JUNIT_OUTPUT_FILE=str(junit))
            r = run(["npm", "run", "test:e2e", "--", "--reporter=list,junit"], self.frontend, env,
                    logs / f"e2e-{i}.log", 1200)
            outcomes = junit_outcomes(junit)
            c = counts(outcomes)
            results.append({"run": i, "passed": c["passed"], "failed": c["failed"], "skipped": c["skipped"],
                            "seconds": r["seconds"],
                            "failed_tests": sorted(k for k, v in outcomes.items() if v["outcome"] == "failed")})
            log(f"e2e run {i}: {c['passed']} passed, {c['failed']} failed")
        tests = max((r["passed"] + r["failed"] + r["skipped"] for r in results), default=0)
        failing = sorted({t for r in results for t in r["failed_tests"]})
        self.metrics["e2e"] = {"tests": tests, "runs": results, "flaky": failing}
        self.save()

    # -------------------------------------------------------------------------- static

    def static(self) -> None:
        self.metrics["static"] = {
            "backend": python_test_stats(self.backend_tests(), self.wt),
            "frontend": ts_test_stats(self.frontend_tests(), self.wt),
            "e2e_files": sorted(str(p.relative_to(self.wt)) for p in self.wt.rglob("*.spec.ts")
                                if "node_modules" not in p.parts and "e2e" in p.parts),
        }
        self.save()


# ----------------------------------------------------------------------- coverage parse


def coverage_py_summary(cov: dict) -> dict:
    t = cov["totals"]
    files = {}
    for path, data in sorted(cov["files"].items()):
        s = data["summary"]
        files[path] = {
            "statements": s["num_statements"], "covered": s["covered_lines"],
            "branches": s.get("num_branches", 0), "covered_branches": s.get("covered_branches", 0),
            "line_pct": round(100 * s["covered_lines"] / s["num_statements"], 1) if s["num_statements"] else 100.0,
            "branch_pct": round(100 * s["covered_branches"] / s["num_branches"], 1) if s.get("num_branches") else None,
        }
    return {
        "line_pct": round(100 * t["covered_lines"] / t["num_statements"], 1),
        "branch_pct": round(100 * t["covered_branches"] / t["num_branches"], 1) if t.get("num_branches") else None,
        "statements": t["num_statements"], "covered": t["covered_lines"],
        "branches": t.get("num_branches"), "covered_branches": t.get("covered_branches"),
        "files": files,
    }


def istanbul_summary(cov: dict, frontend: Path) -> dict:
    total = cov["total"]
    files = {}
    for path, data in sorted(cov.items()):
        if path == "total":
            continue
        rel = str(Path(path).resolve().relative_to(frontend.resolve())) if path.startswith("/") else path
        files[rel] = {k: data[k]["pct"] for k in ("lines", "branches", "functions", "statements")}
    return {
        "line_pct": total["lines"]["pct"], "branch_pct": total["branches"]["pct"],
        "function_pct": total["functions"]["pct"], "statement_pct": total["statements"]["pct"],
        "lines": total["lines"]["total"], "covered_lines": total["lines"]["covered"],
        "branches": total["branches"]["total"], "covered_branches": total["branches"]["covered"],
        "files": files,
    }


# ---------------------------------------------------------------------- static analysis


def _is_status_only(node: ast.Assert) -> bool:
    """`assert r.status_code == 200` and similar: checks only the HTTP status."""
    names = {n.attr for n in ast.walk(node.test) if isinstance(n, ast.Attribute)}
    return bool(names) and names <= {"status_code"}


def python_test_stats(files: list[Path], root: Path) -> dict:
    tests = []
    for path in files:
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) or not node.name.startswith("test"):
                continue
            asserts = [n for n in ast.walk(node) if isinstance(n, ast.Assert)]
            raises = sum(
                1 for n in ast.walk(node)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in ("raises", "warns")
            )
            mock_checks = sum(
                1 for n in ast.walk(node)
                if isinstance(n, ast.Call) and (
                    (isinstance(n.func, ast.Attribute) and n.func.attr.startswith("assert"))
                    or (isinstance(n.func, ast.Name) and n.func.id.startswith("assert"))
                )
            )
            total = len(asserts) + raises + mock_checks
            status_only = bool(asserts) and raises == 0 and mock_checks == 0 and all(_is_status_only(a) for a in asserts)
            tests.append({
                "file": str(path.relative_to(root)), "name": node.name, "assertions": total,
                "status_only": status_only,
            })
    n = len(tests)
    return {
        "test_functions": n,
        "files": len(files),
        "assertions_total": sum(t["assertions"] for t in tests),
        "mean_assertions": round(sum(t["assertions"] for t in tests) / n, 2) if n else 0,
        "no_assertion": sorted(f"{t['file']}::{t['name']}" for t in tests if t["assertions"] == 0),
        "status_code_only": sorted(f"{t['file']}::{t['name']}" for t in tests if t["status_only"]),
        "per_file": {f: sum(1 for t in tests if t["file"] == f) for f in sorted({t["file"] for t in tests})},
    }


_TEST_START = re.compile(r"\b(?:it|test)(?:\.(?:each\([^)]*\)|only|concurrent|fails))?\s*\(")


def _block_end(src: str, start: int) -> int:
    """Index after the parenthesis that closes the call opened just before `start`."""
    depth, i, quote = 1, start, None
    while i < len(src) and depth:
        ch = src[i]
        if quote:
            if ch == "\\":
                i += 1
            elif ch == quote:
                quote = None
        elif ch in "'\"`":
            quote = ch
        elif src.startswith("//", i):
            nl = src.find("\n", i)
            i = len(src) if nl == -1 else nl
            continue
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        i += 1
    return i


def ts_test_stats(files: list[Path], root: Path) -> dict:
    tests = []
    for path in files:
        src = path.read_text()
        for m in _TEST_START.finditer(src):
            end = _block_end(src, m.end())
            body = src[m.end():end]
            tests.append({"file": str(path.relative_to(root)), "assertions": len(re.findall(r"\bexpect\s*[.(]", body)),
                          "title": body[:80].split("\n")[0]})
    n = len(tests)
    return {
        "test_blocks": n,
        "files": len(files),
        "assertions_total": sum(t["assertions"] for t in tests),
        "mean_assertions": round(sum(t["assertions"] for t in tests) / n, 2) if n else 0,
        "no_assertion": [f"{t['file']}: {t['title']}" for t in tests if t["assertions"] == 0],
        "per_file": {f: sum(1 for t in tests if t["file"] == f) for f in sorted({t["file"] for t in tests})},
    }


# ---------------------------------------------------------------------------- summary


def write_summary(m: dict, out: Path) -> None:
    lines = [f"# Evaluation of `{m['ref']}` ({m['commit'][:7]})", ""]
    b, f = m.get("backend", {}), m.get("frontend", {})
    lines += ["## Execution", "", "| Suite | Total | Passed | Failed | Skipped | xfail | Seconds |",
              "|-------|-------|--------|--------|---------|-------|---------|"]
    for name, s in (("Backend (pytest)", b), ("Frontend (Vitest)", f)):
        if s.get("present"):
            c = s["counts"]
            lines.append(f"| {name} | {c['total']} | {c['passed']} | {c['failed']} | {c['skipped']} | {c['xfail']} | {s['run']['seconds']} |")
        else:
            lines.append(f"| {name} | none | | | | | |")
    if m.get("e2e"):
        e = m["e2e"]
        runs = ", ".join(f"{r['passed']}/{r['passed'] + r['failed'] + r['skipped']}" for r in e["runs"])
        lines.append(f"| End-to-end (Playwright) | {e['tests']} | runs: {runs} | | | | |")
        if e["flaky"]:
            lines.append("")
            lines.append("End-to-end tests that failed in at least one run: " + "; ".join(e["flaky"]))
    lines += ["", "## Coverage", "", "| Suite | Line % | Branch % |", "|-------|--------|----------|"]
    if b.get("coverage"):
        lines.append(f"| Backend | {b['coverage']['line_pct']} | {b['coverage']['branch_pct']} |")
    if f.get("coverage"):
        lines.append(f"| Frontend | {f['coverage']['line_pct']} | {f['coverage']['branch_pct']} |")
    if "flaky" in m:
        lines += ["", f"## Stability ({m['flaky'].get('runs_per_suite')} shuffled runs per suite)", ""]
        for layer in ("backend", "frontend"):
            items = m["flaky"].get(layer, [])
            lines.append(f"- {layer}: {len(items)} unstable test(s)" + (": " + ", ".join(items[:10]) if items else ""))
    if "hermetic" in m:
        net = m["hermetic"]["fail_only_without_network"]
        lines += ["", "## Hermeticity", "", f"- backend tests that fail only without network: {len(net)}"]
        lines += [f"  - {t}" for t in net[:20]]
    if "faults" in m:
        fa = m["faults"]
        lines += ["", "## Held-out seeded faults", "",
                  f"Detected {fa['detected']}/{fa['total']} (backend {fa['detected_backend']}/{fa['total_backend']}, "
                  f"frontend {fa['detected_frontend']}/{fa['total_frontend']}; HW1-history faults {fa['detected_history']}/{fa['total_history']}).",
                  "", "| Fault | Detected | Detecting tests |", "|-------|----------|-----------------|"]
        for fid, r in fa["results"].items():
            lines.append(f"| {fid} | {'yes' if r['detected'] else 'no'} | {len(r.get('detected_by', []))} |")
    if "static" in m:
        sb, sf = m["static"]["backend"], m["static"]["frontend"]
        lines += ["", "## Assertions", "",
                  f"- backend: {sb['test_functions']} test functions in {sb['files']} files, {sb['mean_assertions']} assertions per test; "
                  f"{len(sb['no_assertion'])} without assertions; {len(sb['status_code_only'])} that check only the status code",
                  f"- frontend: {sf['test_blocks']} tests in {sf['files']} files, {sf['mean_assertions']} expect() per test; "
                  f"{len(sf['no_assertion'])} without expect()"]
    if m.get("notes"):
        lines += ["", "## Notes", ""] + [f"- {n}" for n in m["notes"]]
    (out / "summary.md").write_text("\n".join(lines) + "\n")


# ------------------------------------------------------------------------------- main


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", required=True)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--scratch", required=True, type=Path)
    ap.add_argument("--steps", default=",".join(ALL_STEPS))
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--e2e-runs", type=int, default=4)
    args = ap.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    phase = Phase(args.ref, out, args.scratch.resolve())
    steps = [s.strip() for s in args.steps.split(",") if s.strip()]
    for step in steps:
        if step not in ALL_STEPS:
            sys.exit(f"unknown step {step}")
    for step in ALL_STEPS:
        if step not in steps:
            continue
        log(f"== {step}")
        {"setup": phase.setup, "backend": phase.backend_main, "frontend": phase.frontend_main,
         "flaky": lambda: phase.flaky(args.runs), "parallel": phase.parallel, "hermetic": phase.hermetic,
         "faults": phase.faults, "static": phase.static, "e2e": lambda: phase.e2e(args.e2e_runs)}[step]()
    write_summary(phase.metrics, out)
    log(f"summary: {out / 'summary.md'}")


if __name__ == "__main__":
    main()
