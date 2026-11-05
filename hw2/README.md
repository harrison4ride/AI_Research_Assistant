# HW2: How the Tests Were Generated and Evaluated

This folder holds the evidence and the tools behind the HW2 report on generating and
improving this app's tests with Claude Code. The tests themselves are in `backend/tests/`,
`frontend/src/`, and `frontend/e2e/`; [docs/TESTING.md](../docs/TESTING.md) explains how
to run them.

## The Experiment

| Tag | Content |
|-----|---------|
| `hw2-baseline` | The application, frozen for the whole experiment |
| `hw2-initial` | The suite that a fresh-context Claude Code agent generated from one prompt |
| `hw2-round1` | After round 1: feedback from the requirements, a correctness review, and coverage |
| `hw2-round2` | After round 2: feedback from running the suite (decisions on suspected bugs, a code review, a parallel run, mutation testing); the final suite |

Each suite is committed exactly as its agent produced it. The application code is the
same at all four tags.

## Evidence

| Folder | Contents |
|--------|----------|
| `evidence/00-baseline/` | Environment, and the list of held-out faults |
| `evidence/01-initial/` | The prompt, the agent's report, the correctness review by five reviewer agents (`review/`, with their prompts), the confirmed bugs, the code review, and the evaluation |
| `evidence/02-round1/` | The feedback and prompt for round 1, the agent's report, the code review of its changes, the parallel-run regression, and the evaluation |
| `evidence/03-round2/` | The feedback and prompt for round 2, the agent's report, run notes, the code review and the experiments that verified it, a spot check of "equivalent" mutants, the final correctness review (`review/`), and the evaluation |
| `evidence/final/` | The three phases compared (`comparison.md`), and a note on rerunning the held-out faults |

Each phase's `eval/` folder holds `metrics.json` (every measure), `summary.md`,
`mutation.json`, and `mutation-survivors.md` (the diff of every surviving mutant). Raw
logs, JUnit files, and coverage data are left out. `evaluation.md` in each phase folder
is the readable summary.

## Tools

| File | Purpose |
|------|---------|
| `tools/evaluate.py` | Measures one phase: checks the tag out into a fresh git worktree, installs from the lock files, and runs the suites with coverage, 5 shuffled runs, 8 parallel workers, no network, the held-out faults, assertion counts, and 4 end-to-end runs |
| `tools/mutation.py` | Mutation testing with mutmut, one mutant at a time. It lists 9 backend modules; 8 yield mutants, because the search router's only function is a decorated route handler, which mutmut does not mutate |
| `tools/compare.py` | Prints the comparison tables in `evidence/final/comparison.md` |
| `tools/build_faults.py` | Builds the held-out fault patches from `hw2-baseline` |
| `tools/faults/` | The 18 held-out faults: one patch each, described in `manifest.json` |
| `tools/stubs/claude` | Stands in for the Claude Code CLI during evaluation; it fails and logs every call, so no test reaches a real LLM |
| `tools/mutmut_support/hw2_reload.py` | A pytest plugin that lets mutmut run the suite several times in one process |
| `tools/review-rubric.md` | The rubric the reviewer agents used |

## Reproduce the Numbers

The tools need the same software as the app (uv, Node.js 22.13 or later, git) and run on
macOS or Linux. `evaluate.py` and `mutation.py` never change your working tree: each tag
is checked out into a worktree inside the scratch folder you name. They use the tool
versions of the original evaluation: mutmut 3.8.1, pytest-cov 7.1.0, pytest-timeout
2.4.0, pytest-randomly 5.0.0, pytest-socket 0.8.1, pytest-xdist 3.8.0, and, when a suite
does not declare it, @vitest/coverage-v8 at the suite's Vitest version.

```bash
git fetch --tags     # the tools check out the hw2-* tags
cd hw2
uv run --no-project --python 3.11 tools/evaluate.py --ref hw2-round2 \
    --out /tmp/hw2-eval/round2 --scratch /tmp/hw2-scratch
uv run --no-project --python 3.11 tools/mutation.py --ref hw2-round2 \
    --out /tmp/hw2-eval/round2 --scratch /tmp/hw2-scratch
python3 tools/compare.py initial=evidence/01-initial/eval \
    round1=evidence/02-round1/eval round2=evidence/03-round2/eval
```

- `evaluate.py` takes about 10 minutes per phase and uses port 8765 for the end-to-end
  runs. Run it on an otherwise idle machine: under heavy load, timing-sensitive tests can
  fail and be counted as fault detections (`evidence/final/faults-rerun.md`).
- `mutation.py` needs the worktree that `evaluate.py` created (the same `--scratch`) and
  runs about 2,800 mutants, about an hour. Add `--rerun-timeouts` to run the mutants that
  timed out again.
- `compare.py` rewrites `evidence/final/chart-data.json` in the current folder.
- Afterwards, `git worktree remove --force /tmp/hw2-scratch/wt-hw2-round2` (or delete
  the scratch folder and run `git worktree prune`) removes the worktree from the
  repository. `--force` is needed because `mutation.py` writes its settings and results
  into the worktree.
