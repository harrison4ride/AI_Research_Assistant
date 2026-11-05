# Surviving mutants (22)

## app.routers.papers.x__merge_llm_metadata__mutmut_14

```diff
--- app/routers/papers.py
+++ app/routers/papers.py
@@ -12,5 +12,5 @@
         paper.authors = authors
     if found.year is not None:
         paper.year = found.year
-    if found.abstract and len(found.abstract.strip()) >= 100:
+    if found.abstract and len(found.abstract.strip()) > 100:
         paper.abstract = found.abstract.strip()
```

## app.routers.papers.x__merge_llm_metadata__mutmut_7

```diff
--- app/routers/papers.py
+++ app/routers/papers.py
@@ -4,7 +4,7 @@
     A title that isn't in the text means the answer can't be trusted, so then
     none of its fields are used.
     """
-    if not (found.title.strip() and pdf.title_on_page(found.title, extracted.text[:15000])):
+    if not (found.title.strip() and pdf.title_on_page(found.title, extracted.text[:15001])):
         return
     paper.title = found.title.strip()
     authors = [a.strip() for a in found.authors if a.strip()]
```

## app.services.arxiv.x__cooldown_error__mutmut_6

```diff
--- app/services/arxiv.py
+++ app/services/arxiv.py
@@ -1,5 +1,5 @@
 def _cooldown_error() -> UpstreamError:
-    wait = max(1, round(_cooldown_until - time.monotonic()))
+    wait = max(2, round(_cooldown_until - time.monotonic()))
     return UpstreamError(
         f"arXiv is limiting requests right now, so it is paused for about {wait} s. Search OpenAlex meanwhile.",
         429,
```

## app.services.arxiv.x_parse_entry__mutmut_49

```diff
--- app/services/arxiv.py
+++ app/services/arxiv.py
@@ -4,7 +4,7 @@
     published = _text(entry.find("a:published", NS))
     pdf_url = None
     for link in entry.findall("a:link", NS):
-        if link.get("title") == "pdf" or link.get("type") == "application/pdf":
+        if link.get("title") == "pdf" or link.get("TYPE") == "application/pdf":
             pdf_url = link.get("href")
     return PaperMeta(
         source="arxiv",
```

## app.services.arxiv.x_parse_entry__mutmut_88

```diff
--- app/services/arxiv.py
+++ app/services/arxiv.py
@@ -9,7 +9,7 @@
     return PaperMeta(
         source="arxiv",
         external_id=arxiv_id,
-        title=_text(entry.find("a:title", NS)) or "(untitled)",
+        title=_text(entry.find("a:title", NS)) or "XX(untitled)XX",
         authors=[
             name
             for a in entry.findall("a:author", NS)
```

## app.services.llm.x__describe__mutmut_11

```diff
--- app/services/llm.py
+++ app/services/llm.py
@@ -15,4 +15,4 @@
         return f"The Anthropic API returned an error ({exc.status_code}). Try again shortly."
     if isinstance(exc, anthropic.APIConnectionError):
         return "Could not reach the Anthropic API. Check your network connection."
-    return "The language model request failed."
+    return "XXThe language model request failed.XX"
```

## app.services.llm.x__describe__mutmut_12

```diff
--- app/services/llm.py
+++ app/services/llm.py
@@ -15,4 +15,4 @@
         return f"The Anthropic API returned an error ({exc.status_code}). Try again shortly."
     if isinstance(exc, anthropic.APIConnectionError):
         return "Could not reach the Anthropic API. Check your network connection."
-    return "The language model request failed."
+    return "the language model request failed."
```

## app.services.llm.x__describe__mutmut_13

```diff
--- app/services/llm.py
+++ app/services/llm.py
@@ -15,4 +15,4 @@
         return f"The Anthropic API returned an error ({exc.status_code}). Try again shortly."
     if isinstance(exc, anthropic.APIConnectionError):
         return "Could not reach the Anthropic API. Check your network connection."
-    return "The language model request failed."
+    return "THE LANGUAGE MODEL REQUEST FAILED."
```

## app.services.llm.x__plausible__mutmut_4

```diff
--- app/services/llm.py
+++ app/services/llm.py
@@ -1,4 +1,4 @@
 def _plausible(meta: ExtractedMetadata) -> ExtractedMetadata:
-    if meta.year is not None and not (1900 <= meta.year <= date.today().year):
+    if meta.year is not None and not (1901 <= meta.year <= date.today().year):
         meta.year = None
     return meta
```

## app.services.llm.x__plausible__mutmut_5

```diff
--- app/services/llm.py
+++ app/services/llm.py
@@ -1,4 +1,4 @@
 def _plausible(meta: ExtractedMetadata) -> ExtractedMetadata:
-    if meta.year is not None and not (1900 <= meta.year <= date.today().year):
+    if meta.year is not None and not (1900 < meta.year <= date.today().year):
         meta.year = None
     return meta
```

## app.services.llm.x__plausible__mutmut_6

```diff
--- app/services/llm.py
+++ app/services/llm.py
@@ -1,4 +1,4 @@
 def _plausible(meta: ExtractedMetadata) -> ExtractedMetadata:
-    if meta.year is not None and not (1900 <= meta.year <= date.today().year):
+    if meta.year is not None and not (1900 <= meta.year < date.today().year):
         meta.year = None
     return meta
```

## app.services.llm.x__stream_api__mutmut_59

```diff
--- app/services/llm.py
+++ app/services/llm.py
@@ -36,7 +36,7 @@
     log.info(
         "Claude %s: in=%s cache_read=%s cache_write=%s out=%s stop=%s",
         final.model, usage.input_tokens, usage.cache_read_input_tokens,
-        usage.cache_creation_input_tokens, usage.output_tokens, final.stop_reason,
+        usage.cache_creation_input_tokens, None, final.stop_reason,
     )
     if final.stop_reason == "refusal":
         raise LlmError("The model declined to answer this request.")
```

## app.services.llm.x_credentials_available__mutmut_11

```diff
--- app/services/llm.py
+++ app/services/llm.py
@@ -8,4 +8,4 @@
         return True
     if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
         return True
-    return bool(os.environ.get("ANTHROPIC_PROFILE")) or (Path.home() / ".config" / "anthropic").is_dir()
+    return bool(None) or (Path.home() / ".config" / "anthropic").is_dir()
```

## app.services.openalex.x_parse_work__mutmut_20

```diff
--- app/services/openalex.py
+++ app/services/openalex.py
@@ -2,7 +2,7 @@
     primary = work.get("primary_location") or {}
     best_oa = work.get("best_oa_location") or {}
     doi = work.get("doi")
-    openalex_id = (work.get("id") or "").rsplit("/", 1)[-1] or None
+    openalex_id = (work.get("id") or "").rsplit("/", )[-1] or None
     return PaperMeta(
         source="openalex",
         external_id=openalex_id,
```

## app.services.openalex.x_parse_work__mutmut_90

```diff
--- app/services/openalex.py
+++ app/services/openalex.py
@@ -15,7 +15,7 @@
         year=work.get("publication_year"),
         abstract=rebuild_abstract(work.get("abstract_inverted_index")),
         url=primary.get("landing_page_url") or doi or work.get("id"),
-        pdf_url=best_oa.get("pdf_url") or primary.get("pdf_url"),
+        pdf_url=best_oa.get("pdf_url") or primary.get(None),
         venue=(primary.get("source") or {}).get("display_name"),
         doi=doi.removeprefix("https://doi.org/") if doi else None,
     )
```

## app.services.openalex.x_parse_work__mutmut_91

```diff
--- app/services/openalex.py
+++ app/services/openalex.py
@@ -15,7 +15,7 @@
         year=work.get("publication_year"),
         abstract=rebuild_abstract(work.get("abstract_inverted_index")),
         url=primary.get("landing_page_url") or doi or work.get("id"),
-        pdf_url=best_oa.get("pdf_url") or primary.get("pdf_url"),
+        pdf_url=best_oa.get("pdf_url") or primary.get("XXpdf_urlXX"),
         venue=(primary.get("source") or {}).get("display_name"),
         doi=doi.removeprefix("https://doi.org/") if doi else None,
     )
```

## app.services.openalex.x_parse_work__mutmut_92

```diff
--- app/services/openalex.py
+++ app/services/openalex.py
@@ -15,7 +15,7 @@
         year=work.get("publication_year"),
         abstract=rebuild_abstract(work.get("abstract_inverted_index")),
         url=primary.get("landing_page_url") or doi or work.get("id"),
-        pdf_url=best_oa.get("pdf_url") or primary.get("pdf_url"),
+        pdf_url=best_oa.get("pdf_url") or primary.get("PDF_URL"),
         venue=(primary.get("source") or {}).get("display_name"),
         doi=doi.removeprefix("https://doi.org/") if doi else None,
     )
```

## app.services.openalex.x_search__mutmut_31

```diff
--- app/services/openalex.py
+++ app/services/openalex.py
@@ -15,7 +15,7 @@
     except httpx.TimeoutException as exc:
         raise UpstreamError("OpenAlex timed out, please try again.", 504) from exc
     except httpx.HTTPError as exc:
-        log.warning("OpenAlex request failed: %r", exc)
+        log.warning("OpenAlex request failed: %r", None)
         raise UpstreamError("Could not reach OpenAlex. Check your connection and try again.") from exc
     if resp.status_code == 429:
         raise UpstreamError("OpenAlex rate limit reached. Set OPENALEX_API_KEY or try arXiv.", 429)
```

## app.services.openalex.x_search__mutmut_32

```diff
--- app/services/openalex.py
+++ app/services/openalex.py
@@ -15,7 +15,7 @@
     except httpx.TimeoutException as exc:
         raise UpstreamError("OpenAlex timed out, please try again.", 504) from exc
     except httpx.HTTPError as exc:
-        log.warning("OpenAlex request failed: %r", exc)
+        log.warning(exc)
         raise UpstreamError("Could not reach OpenAlex. Check your connection and try again.") from exc
     if resp.status_code == 429:
         raise UpstreamError("OpenAlex rate limit reached. Set OPENALEX_API_KEY or try arXiv.", 429)
```

## app.services.openalex.x_search__mutmut_33

```diff
--- app/services/openalex.py
+++ app/services/openalex.py
@@ -15,7 +15,7 @@
     except httpx.TimeoutException as exc:
         raise UpstreamError("OpenAlex timed out, please try again.", 504) from exc
     except httpx.HTTPError as exc:
-        log.warning("OpenAlex request failed: %r", exc)
+        log.warning("OpenAlex request failed: %r", )
         raise UpstreamError("Could not reach OpenAlex. Check your connection and try again.") from exc
     if resp.status_code == 429:
         raise UpstreamError("OpenAlex rate limit reached. Set OPENALEX_API_KEY or try arXiv.", 429)
```

## app.services.openalex.x_search__mutmut_34

```diff
--- app/services/openalex.py
+++ app/services/openalex.py
@@ -15,7 +15,7 @@
     except httpx.TimeoutException as exc:
         raise UpstreamError("OpenAlex timed out, please try again.", 504) from exc
     except httpx.HTTPError as exc:
-        log.warning("OpenAlex request failed: %r", exc)
+        log.warning("XXOpenAlex request failed: %rXX", exc)
         raise UpstreamError("Could not reach OpenAlex. Check your connection and try again.") from exc
     if resp.status_code == 429:
         raise UpstreamError("OpenAlex rate limit reached. Set OPENALEX_API_KEY or try arXiv.", 429)
```

## app.services.openalex.x_search__mutmut_35

```diff
--- app/services/openalex.py
+++ app/services/openalex.py
@@ -15,7 +15,7 @@
     except httpx.TimeoutException as exc:
         raise UpstreamError("OpenAlex timed out, please try again.", 504) from exc
     except httpx.HTTPError as exc:
-        log.warning("OpenAlex request failed: %r", exc)
+        log.warning("openalex request failed: %r", exc)
         raise UpstreamError("Could not reach OpenAlex. Check your connection and try again.") from exc
     if resp.status_code == 429:
         raise UpstreamError("OpenAlex rate limit reached. Set OPENALEX_API_KEY or try arXiv.", 429)
```
