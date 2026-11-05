"""One scratch folder per test process, for the app's database and stored PDFs.

Every process that runs tests gets a folder of its own: each pytest-xdist worker, and each
child forked from a process that already loaded the app (as mutation testers do). Processes
must not share one, or one process's clean-up deletes the database another is using. A
second pytest session in the same process reuses the folder: pytest imports conftest.py
again for each session, but this module stays imported.

app/db.py binds its engine to <DATA_DIR>/app.db when it is imported, once per process; in a
forked child that happened in the parent, before the fork. connect_engine_to() makes the
engine open its connections on another file from then on, so a forked child (or a test that
starts the app on an older database) uses its own file with every module that holds the
engine or SessionLocal.
"""

import atexit
import os
import shutil
import tempfile
from pathlib import Path

from sqlalchemy import event
from sqlalchemy.engine import Engine

_pid: int | None = None
_folder: Path | None = None
_database: Path | None = None


def folder() -> Path:
    """This process's scratch folder, made the first time a process asks for it.

    conftest.py removes it after each session; it is also removed when the process exits,
    in case pytest stopped before a session ended (e.g. on a usage error).
    """
    global _pid, _folder
    if _pid != os.getpid():
        _pid, _folder = os.getpid(), Path(tempfile.mkdtemp(prefix="ra-backend-tests-"))
        atexit.register(_remove, _pid, _folder)
    return _folder


def _remove(pid: int, path: Path) -> None:
    if os.getpid() == pid:  # not in a forked child, which inherits this handler
        shutil.rmtree(path, ignore_errors=True)


def database() -> Path | None:
    """The file the engine opens its connections on (set by connect_engine_to)."""
    return _database


def connect_engine_to(engine: Engine, database: Path) -> None:
    """Open the engine's connections on the SQLite file `database` from now on."""
    global _database
    _database = database
    # Pooled connections still point at the previous file, and in a forked child they were
    # opened by the parent: drop them without closing them (SQLAlchemy's advice after a fork).
    engine.dispose(close=False)
    if not event.contains(engine, "do_connect", _open_database):
        event.listen(engine, "do_connect", _open_database)


def _open_database(dialect, connection_record, cargs, cparams) -> None:
    if _database is not None:
        cargs[0] = str(_database)  # pysqlite's connect(database, **cparams)
