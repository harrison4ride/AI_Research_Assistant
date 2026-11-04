"""The app's module-level state, which lives as long as the process, and its reset.

Every test starts from fresh values (conftest.py), so no test sees caches, locks,
cooldowns, or background tasks left by another. test_isolation.py fails when the
app gains module-level state that is not reset here.
"""

import asyncio
import inspect
import sys
from collections import OrderedDict

import pytest

from app import config
from app.routers import search
from app.services import arxiv, claude_code, fulltext, http, llm


def fresh_values() -> dict[tuple[object, str], object]:
    return {
        (search, "_cache"): OrderedDict(),
        (arxiv, "_rate_lock"): asyncio.Lock(),
        (arxiv, "_last_finished"): 0.0,
        (arxiv, "_cooldown_until"): 0.0,
        (fulltext, "_locks"): {},
        (claude_code, "_status_cache"): None,
        (claude_code, "_status_task"): None,
        (claude_code, "_background"): set(),
        (http, "_client"): None,
    }


# Functions whose results the app caches (functools.lru_cache).
CACHED_FUNCTIONS = [llm.get_client]
# Kept for the whole session on purpose: the tests pin the settings once, and
# change single values with monkeypatch.
SHARED = {(config.__name__, "get_settings")}
# Computed once at import and never changed.
CONSTANTS = {("app.main", "_hint")}


def reset(monkeypatch: pytest.MonkeyPatch) -> None:
    for (module, name), value in fresh_values().items():
        monkeypatch.setattr(module, name, value)
    for function in CACHED_FUNCTIONS:
        function.cache_clear()


def reset_names() -> set[tuple[str, str]]:
    names = {(module.__name__, name) for module, name in fresh_values()}
    names |= {(function.__module__, function.__name__) for function in CACHED_FUNCTIONS}
    return names | SHARED | CONSTANTS


def state_in_the_app() -> set[tuple[str, str]]:
    """(module, name) of every cached function and private lower-case variable in app/."""
    found = set()
    for module_name, module in list(sys.modules.items()):
        if module_name != "app" and not module_name.startswith("app."):
            continue
        for name, value in vars(module).items():
            if name.startswith("__"):
                continue
            if hasattr(value, "cache_clear") and getattr(value, "__module__", None) == module_name:
                found.add((module_name, name))
            elif (name.startswith("_") and name == name.lower()
                  and not (inspect.ismodule(value) or inspect.isclass(value) or inspect.isroutine(value))):
                found.add((module_name, name))
    return found
