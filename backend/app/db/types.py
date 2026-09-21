"""Portable column types.

PostgreSQL is the production datastore and its native ``JSONB`` and ``UUID``
types are used there. The models are written against these wrappers instead of
the dialect types directly so the same schema also runs on SQLite, which lets
the whole pipeline be exercised end to end -- and demonstrated -- without
standing up Postgres and Redis first.
"""

from __future__ import annotations

import uuid as uuid_module
from typing import Any

from sqlalchemy import CHAR, JSON
from sqlalchemy.dialects import postgresql
from sqlalchemy.types import TypeDecorator

# JSONB on PostgreSQL, plain JSON elsewhere. Identical Python-side behaviour.
JSONB = JSON().with_variant(postgresql.JSONB(), "postgresql")


class UUID(TypeDecorator):
    """Native ``uuid`` on PostgreSQL, ``CHAR(36)`` elsewhere.

    Values are always handed back to the application as ``uuid.UUID``, so
    nothing downstream has to care which backend is in use.
    """

    impl = CHAR
    cache_ok = True

    def __init__(self, as_uuid: bool = True) -> None:
        self.as_uuid = as_uuid
        super().__init__()

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(postgresql.UUID(as_uuid=True))
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value: Any, dialect) -> Any:
        if value is None:
            return None
        if not isinstance(value, uuid_module.UUID):
            value = uuid_module.UUID(str(value))
        return value if dialect.name == "postgresql" else str(value)

    def process_result_value(self, value: Any, dialect) -> Any:
        if value is None:
            return None
        if isinstance(value, uuid_module.UUID):
            return value
        return uuid_module.UUID(str(value))
