#!/bin/sh
set -e
python -m alembic upgrade head || python -m app.db.migrate
exec "$@"
