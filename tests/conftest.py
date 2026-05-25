"""Shared pytest fixtures for the cache tests.

Point the cache at a throwaway SQLite file *before* importing food_cache, so
its module-level engine never touches the real db/recipe_cache.db.
"""

import os
import tempfile

_TMP_DIR = tempfile.mkdtemp(prefix="recipe_cache_tests_")
os.environ["RECIPE_DB_URL"] = f"sqlite:///{_TMP_DIR}/test_cache.db"

import pytest
from sqlmodel import SQLModel

from src import food_cache


@pytest.fixture(autouse=True)
def fresh_db():
    """Give each test an empty schema on the shared temp database."""
    SQLModel.metadata.drop_all(food_cache._engine)
    SQLModel.metadata.create_all(food_cache._engine)
    food_cache._schema_ready = True
    yield
    SQLModel.metadata.drop_all(food_cache._engine)
