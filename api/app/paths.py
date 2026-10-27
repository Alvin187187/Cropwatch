import os
from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def data_dir() -> Path:
    return Path(os.environ.get("DATA_DIR", repo_root() / "data"))


def rules_dir() -> Path:
    return Path(os.environ.get("RULES_DIR", repo_root() / "rules"))
