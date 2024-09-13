from __future__ import annotations

import os
from pathlib import Path

LOCAL_DB_PATH: Path | None = None
OUT_DB_PATH: Path | None = None


def set_paths(*, local_db_path: Path | str | None = None, out_db_path: Path | str | None = None) -> None:
    """
    two ways are provided to set the paths:
    1. set the paths directly in the function (before other modules are imported)
    2. set the paths in the environment variables PYLAB_DB_LOCAL and PYLAB_DB_OUT
    """
    global LOCAL_DB_PATH, OUT_DB_PATH
    if local_db_path is not None:
        LOCAL_DB_PATH = Path(local_db_path)
    else:
        if os.getenv("PYLAB_DB_LOCAL") is None:
            print("PYLAB_DB_LOCAL not set")
        else:
            LOCAL_DB_PATH = Path(os.getenv("PYLAB_DB_LOCAL"))
            print(f"read from PYLAB_DB_LOCAL:{LOCAL_DB_PATH}")

    if out_db_path is not None:
        OUT_DB_PATH = Path(out_db_path)
    else:
        if os.getenv("PYLAB_DB_LOCAL") is None:
            print("PYLAB_DB_LOCAL not set")
        else:
            OUT_DB_PATH = Path(os.getenv("PYLAB_DB_OUT"))
            print(f"read from PYLAB_DB_OUT:{OUT_DB_PATH}")


set_paths()
