import os

import psycopg
from psycopg.rows import dict_row


def database_url() -> str:
    return os.environ.get(
        "DATABASE_URL",
        "postgresql://cropwatch:cropwatch@localhost:5432/cropwatch",
    )


def connect():
    return psycopg.connect(database_url(), row_factory=dict_row)
