### Execution (clean checkout)

| Measure | initial | round1 | round2 |
|---|---|---|---|
| Backend tests | 360 | 458 | 558 |
| Backend passed | 360 | 448 | 553 |
| Backend failed | 0 | 0 | 0 |
| Backend xfail (known app bugs) | 0 | 10 | 5 |
| Frontend tests | 148 | 189 | 190 |
| Frontend passed | 148 | 189 | 190 |
| Frontend failed | 0 | 0 | 0 |
| End-to-end tests | 14 | 15 | 15 |
| End-to-end runs passing all | 3/4 | 4/4 | 4/4 |
| Backend time (s) | 17.4 | 22.6 | 24.3 |
| Frontend time (s) | 6.5 | 11.4 | 10.4 |

### Coverage

| Measure | initial | round1 | round2 |
|---|---|---|---|
| Backend line | 94.4% | 97.0% | 98.6% |
| Backend branch | 87.5% | 91.7% | 95.7% |
| Frontend line | 81.2% | 94.62% | 94.78% |
| Frontend branch | 78.47% | 86.09% | 86.09% |

### Stability and isolation

| Measure | initial | round1 | round2 |
|---|---|---|---|
| Unstable unit tests (5 shuffled runs) | 0 | 0 | 0 |
| Backend tests failing without network | 0 | 0 | 0 |
| Calls to the claude stub | 0 | 0 | 0 |

### Mutation testing

| Measure | initial | round1 | round2 |
|---|---|---|---|
| Mutation score (killed / all) | 76.1% | 77.6% | 89.4% |
| Surviving mutants | 661 | 619 | 289 |

### Assertions

| Measure | initial | round1 | round2 |
|---|---|---|---|
| Backend test functions | 257 | 304 | 361 |
| Backend assertions per test | 2.39 | 2.69 | 2.59 |
| Backend status-code-only tests | 4 | 3 | 3 |
| Frontend test blocks | 140 | 169 | 166 |
| Frontend expect() per test | 2.29 | 2.55 | 2.59 |

### Mutation score per module (killed / all mutants)

| Module | initial | round1 | round2 |
|---|---|---|---|
| routers.assistant | 80.1% | 84.9% | 89.7% |
| routers.papers | 78.3% | 81.4% | 92.5% |
| services.arxiv | 83.8% | 87.2% | 96.8% |
| services.cache | 81.0% | 83.3% | 90.5% |
| services.fulltext | 73.4% | 78.2% | 84.5% |
| services.llm | 76.6% | 75.5% | 85.4% |
| services.openalex | 93.8% | 93.8% | 96.4% |
| services.pdf | 67.2% | 68.4% | 88.2% |

