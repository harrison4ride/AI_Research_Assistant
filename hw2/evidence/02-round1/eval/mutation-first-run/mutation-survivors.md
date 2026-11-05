# Surviving mutants (9)

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

## app.services.llm.x__extract_api__mutmut_45

```diff
--- app/services/llm.py
+++ app/services/llm.py
@@ -16,6 +16,6 @@
     except Exception as exc:  # API errors, missing credentials, or unparseable JSON output
         log.info("LLM metadata extraction skipped: %r", exc)
         return None
-    if response.stop_reason != "end_turn" or response.parsed_output is None:
+    if response.stop_reason != "end_turn" and response.parsed_output is None:
         return None
     return _plausible(response.parsed_output)
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

## app.services.llm.x_credentials_available__mutmut_18

```diff
--- app/services/llm.py
+++ app/services/llm.py
@@ -8,4 +8,4 @@
         return True
     if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
         return True
-    return bool(os.environ.get("ANTHROPIC_PROFILE")) or (Path.home() / ".config" / "anthropic").is_dir()
+    return bool(os.environ.get("ANTHROPIC_PROFILE")) or (Path.home() / ".CONFIG" / "anthropic").is_dir()
```
