"""Build the held-out seeded-fault set for HW2 as patch files.

Each fault is a small, realistic bug that violates documented intended behavior
of the app at tag hw2-baseline. During the experiment the patches lived outside the
repository, so the agents that generated and improved the tests never saw them; they
were added to the repository's hw2/ folder afterwards.

Usage: python build_faults.py <repo> <worktree-dir> <out-dir>
"""

import json
import subprocess
import sys
from pathlib import Path

# origin: "history" = a bug that HW1's code reviews found and fixed (re-introduced
# here, see docs/DEVLOG.md); "new" = written fresh for HW2.
FAULTS = [
    # ---------------- backend ----------------
    {
        "id": "B01", "layer": "backend", "origin": "history (DEVLOG M1 #1)",
        "file": "backend/app/services/openalex.py",
        "summary": "OpenAlex HTML-tag stripping deletes text between '<' and '>'",
        "violates": "F1: search results show the abstract; text such as 'p < 0.05 when n > 30' must survive",
        "old": '_TAG_RE = re.compile(r"</?[A-Za-z][\\w:.-]*(?:\\s[^<>]*)?/?>")',
        "new": '_TAG_RE = re.compile(r"<[^>]+>")',
    },
    {
        "id": "B02", "layer": "backend", "origin": "history (DEVLOG M1 design note)",
        "file": "backend/app/services/arxiv.py",
        "summary": "arXiv query builder keeps stopwords in the AND clause",
        "violates": "F1: 'attention is all you need' must find the paper; arXiv drops stopwords, so an AND on one matches nothing",
        "old": 'words = [w for w in re.split(r"[\\s-]+", clean) if w and w.lower() not in STOPWORDS]',
        "new": 'words = [w for w in re.split(r"[\\s-]+", clean) if w]',
    },
    {
        "id": "B03", "layer": "backend", "origin": "history (DEVLOG M1 #2)",
        "file": "backend/app/services/arxiv.py",
        "summary": "arXiv error feeds (HTTP 200 with an /api/errors entry) are returned as search results",
        "violates": "F1 error handling: a rejected query must surface as an error, not as a fake paper",
        "old": '    if error := _api_error(root):\n        raise UpstreamError(f"arXiv rejected the query: {error}", 400)\n    return root',
        "new": "    return root",
    },
    {
        "id": "B04", "layer": "backend", "origin": "history (DEVLOG M2 #8)",
        "file": "backend/app/routers/papers.py",
        "summary": "Duplicate detection ignores DOIs, so the same paper saved from arXiv and OpenAlex becomes two entries",
        "violates": "F2: saving a paper that is already in the library returns the existing entry",
        "old": (
            "    conditions = [(Paper.source == meta.source) & (Paper.external_id == meta.external_id)]\n"
            "    dois = set()\n"
            "    if meta.doi:\n"
            "        dois.add(meta.doi.lower())\n"
            "        if m := ARXIV_DOI_RE.match(meta.doi):\n"
            '            conditions.append((Paper.source == "arxiv") & (Paper.external_id == m.group(1)))\n'
            '    if meta.source == "arxiv" and meta.external_id:\n'
            '        dois.add(f"10.48550/arxiv.{meta.external_id}".lower())\n'
            "    if dois:\n"
            "        conditions.append(func.lower(Paper.doi).in_(dois))\n"
        ),
        "new": "    conditions = [(Paper.source == meta.source) & (Paper.external_id == meta.external_id)]\n",
    },
    {
        "id": "B05", "layer": "backend", "origin": "history (DEVLOG M3 #1)",
        "file": "backend/app/routers/papers.py",
        "summary": "PATCH with authors=null stores NULL, after which reading the paper fails with 500",
        "violates": "F3: the user can correct extracted metadata; clearing authors must not break the paper",
        "old": '        if field == "authors" and value is None:\n            value = []  # the column is a non-null list\n',
        "new": "",
    },
    {
        "id": "B06", "layer": "backend", "origin": "new",
        "file": "backend/app/routers/papers.py",
        "summary": "Library filter no longer matches author names",
        "violates": "F2: the library filter matches title, author, or abstract (README, LibraryPage placeholder)",
        "old": '        or needle in _fold(paper.abstract or "")\n        or any(needle in _fold(author) for author in paper.authors or [])\n',
        "new": '        or needle in _fold(paper.abstract or "")\n',
    },
    {
        "id": "B07", "layer": "backend", "origin": "new",
        "file": "backend/app/services/fulltext.py",
        "summary": "PDF signature check is off by one: a file that starts with %PDF- is rejected as not a PDF",
        "violates": "F3: uploading a normal PDF works",
        "old": '    return b"%PDF-" in data[:1024]',
        "new": '    return data[:1024].find(b"%PDF-") > 0',
    },
    {
        "id": "B08", "layer": "backend", "origin": "new",
        "file": "backend/app/routers/assistant.py",
        "summary": "Q&A history is sent to the model newest-first",
        "violates": "F5: follow-up questions are answered with the earlier turns as context, in order",
        "old": "    ))[::-1]\n",
        "new": "    ))\n",
    },
    {
        "id": "B09", "layer": "backend", "origin": "new",
        "file": "backend/app/services/llm.py",
        "summary": "Prompt uses the abstract whenever one exists, even when the full text is available",
        "violates": "F4: the summary must be based on the paper's content, not only its metadata",
        "old": "    truncated = False\n    if full_text:\n",
        "new": "    truncated = False\n    if full_text and not abstract:\n",
    },
    {
        "id": "B10", "layer": "backend", "origin": "new",
        "file": "backend/app/services/cache.py",
        "summary": "Cache cleanup also deletes saved library papers that were not opened recently",
        "violates": "F2: saved papers persist; only papers opened from search and never saved are pruned",
        "old": "        Paper.in_library.is_(False),\n        func.coalesce(",
        "new": "        func.coalesce(",
    },
    {
        "id": "B11", "layer": "backend", "origin": "new",
        "file": "backend/app/routers/search.py",
        "summary": "Search cache key ignores the source, so switching arXiv/OpenAlex returns the other source's cached results",
        "violates": "F1: results come from the selected search source",
        "old": '    key = (source, " ".join(query.split()), page, per_page)',
        "new": '    key = (" ".join(query.split()), page, per_page)',
    },
    {
        "id": "B12", "layer": "backend", "origin": "new",
        "file": "backend/app/routers/papers.py",
        "summary": "Library list includes papers that were only opened for reading, never saved",
        "violates": "F2: the library shows the papers the user saved",
        "old": "        select(Paper)\n        .where(Paper.in_library.is_(True))\n",
        "new": "        select(Paper)\n",
    },
    # ---------------- frontend ----------------
    {
        "id": "F01", "layer": "frontend", "origin": "history (DEVLOG M1 #5)",
        "file": "frontend/src/types.ts",
        "summary": "paperKey falls back to the title before the URL/DOI, so different untitled papers collide",
        "violates": "F1: every search result keeps its own identity (save state, list keys)",
        "old": "  return sourceKey(p.source, p.external_id ?? p.url ?? p.doi ?? p.title)",
        "new": "  return sourceKey(p.source, p.external_id ?? p.title)",
    },
    {
        "id": "F02", "layer": "frontend", "origin": "history (DEVLOG M0 #6)",
        "file": "frontend/src/api.ts",
        "summary": "Validation errors (FastAPI 422 detail arrays) lose their message; only the status text is shown",
        "violates": "Error handling: the user sees what was wrong with the request",
        "old": "  if (Array.isArray(detail)) {",
        "new": "  if (Array.isArray(detail) && detail.length > 1) {",
    },
    {
        "id": "F03", "layer": "frontend", "origin": "history (DEVLOG M0 #5)",
        "file": "frontend/src/router.ts",
        "summary": "Routes with a trailing slash (#/library/, #/paper/3/) fall back to the search page",
        "violates": "Navigation: a bookmarked or refreshed URL opens the same page",
        "old": "  const path = hash.replace(/^#/, '').replace(/\\/+$/, '')",
        "new": "  const path = hash.replace(/^#/, '')",
    },
    {
        "id": "F04", "layer": "frontend", "origin": "new",
        "file": "frontend/src/api.ts",
        "summary": "Stream reader drops the last event when the stream does not end with a newline",
        "violates": "F4/F5: every streamed event, including the final one, is delivered",
        "old": "  if (buffer.trim()) onEvent(JSON.parse(buffer) as StreamEvent)\n",
        "new": "",
    },
    {
        "id": "F05", "layer": "frontend", "origin": "new",
        "file": "frontend/src/useLlmStream.ts",
        "summary": "A 'reset' event (fallback model restarted) does not clear the partial text",
        "violates": "F4/F5: after a fallback, only the new model's answer is shown",
        "old": "          case 'reset':\n            setText('')\n            break\n",
        "new": "          case 'reset':\n            break\n",
    },
    {
        "id": "F06", "layer": "frontend", "origin": "new",
        "file": "frontend/src/components/ChatPanel.tsx",
        "summary": "The question is put back into the input after a successful answer instead of after a failure",
        "violates": "F5: after an answer the input is empty; after a failure the question is kept for retry",
        "old": "    if (!ok) setInput((current) => current || q)",
        "new": "    if (ok) setInput((current) => current || q)",
    },
]


def git(*args: str, cwd: Path) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


def main() -> None:
    repo, wt, out = (Path(a).resolve() for a in sys.argv[1:4])
    out.mkdir(parents=True, exist_ok=True)
    if not wt.exists():
        git("worktree", "add", "--detach", str(wt), "hw2-baseline", cwd=repo)
    manifest = []
    for fault in FAULTS:
        path = wt / fault["file"]
        text = path.read_text()
        count = text.count(fault["old"])
        if count != 1:
            sys.exit(f"{fault['id']}: expected exactly one match in {fault['file']}, found {count}")
        path.write_text(text.replace(fault["old"], fault["new"]))
        patch = git("diff", "--", fault["file"], cwd=wt)
        git("checkout", "--", fault["file"], cwd=wt)
        (out / f"{fault['id']}.patch").write_text(patch)
        manifest.append({k: v for k, v in fault.items() if k not in ("old", "new")})
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"wrote {len(manifest)} patches to {out}")


if __name__ == "__main__":
    main()
