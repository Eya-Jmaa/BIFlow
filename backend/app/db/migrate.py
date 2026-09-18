#!/usr/bin/env python
"""Create schema then start the API."""
import subprocess
import sys

from app.db.base import Base
from app.db.session import engine
import app.models  # noqa: F401


def migrate() -> None:
    try:
        subprocess.check_call([sys.executable, "-m", "alembic", "upgrade", "head"])
    except Exception:
        Base.metadata.create_all(bind=engine)


if __name__ == "__main__":
    migrate()
