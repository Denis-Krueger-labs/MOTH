import pytest

from app.db import database


@pytest.fixture
def test_database(tmp_path, monkeypatch):
    database_path = tmp_path / "test_moth.db"

    monkeypatch.setattr(
        database,
        "DATABASE_PATH",
        database_path,
    )

    database.initialize_database()

    yield database_path