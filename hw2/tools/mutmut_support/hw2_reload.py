"""Pytest plugin used only by the mutation-testing harness.

mutmut runs pytest several times in one Python process. A suite whose conftest
deletes its temporary data folder at session end, while modules such as app.db
stay cached, cannot start a second session in that process. Dropping every
module loaded from the project before each session makes each session import
the app (and the tests) fresh, exactly as a separate `pytest` run would.
"""

import os
import sys

import pytest


@pytest.hookimpl(tryfirst=True)
def pytest_load_initial_conftests(early_config, parser, args):
    root = os.getcwd() + os.sep
    for name, module in list(sys.modules.items()):
        if (getattr(module, "__file__", None) or "").startswith(root):
            del sys.modules[name]
