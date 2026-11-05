# Rerun of the held-out faults on an idle machine (2026-11-04, 22:47 to 22:56)

Why: in round 1's evaluation, fault F01 (`paperKey` falls back to the title first) was
"detected" by four tests. Three of them (two SearchPage paging tests and one LibraryPage
test) passed with F01 applied when run alone, as a whole file, and in three quiet runs of
the whole frontend suite. Their failures in the original fault run were timeouts under
load (one failed after 1,034 ms on a `findBy` with the default 1,000 ms limit).

What: the fault step of `tools/evaluate.py` (`--steps faults`) for all three phases, one
after another, with nothing else running. The original results are kept in each phase's
`eval/metrics-before-faults-rerun.json` and `eval/logs/faults-first-run/`.

Result: the same detected faults in every phase (17 of 18; F02 missed). The only change is
round 1's F01, now detected by one test instead of four
(`src/router.test.ts::paperKey > falls back to the URL, then the DOI, then the title`). So
the faults caught by only one test are 8 (initial), 7 (round 1), and 6 (round 2); round 1's
evaluation had reported 6.
