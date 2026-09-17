import pytest

from app.db import database
from app.db import events


@pytest.fixture(autouse=True)
def test_database(
    tmp_path,
    monkeypatch,
):
    database_path = (
        tmp_path / "test_moth.db"
    )

    monkeypatch.setattr(
        database,
        "DATABASE_PATH",
        database_path,
    )

    database.initialize_database()
    events.initialize_event_history()

    yield database_path