from threading import Event

from fastapi.testclient import TestClient

from app import main


def test_lifespan_starts_and_stops_retry_scheduler(
    test_database,
    monkeypatch,
):
    started = Event()
    stopped = Event()

    async def fake_scheduler(
        stop_event,
    ):
        started.set()

        await stop_event.wait()

        stopped.set()

    monkeypatch.setattr(
        main.scheduler,
        "run_retry_scheduler",
        fake_scheduler,
    )

    with TestClient(main.app) as client:
        assert started.wait(timeout=1)

        task = (
            client.app.state
            .retry_scheduler_task
        )

        stop_event = (
            client.app.state
            .retry_scheduler_stop_event
        )

        assert task.done() is False
        assert stop_event.is_set() is False

        response = client.get("/")

        assert response.status_code == 200

        assert response.json() == {
            "name": "MOTH",
            "status": "alive",
            "message": (
                "mof is watching the lämp"
            ),
        }

    assert stopped.wait(timeout=1)
    assert task.done() is True
    assert stop_event.is_set() is True


def test_lifespan_initializes_database(
    test_database,
    monkeypatch,
):
    initialize_calls = []
    stopped = Event()

    def fake_initialize_database():
        initialize_calls.append(
            "initialized"
        )

    async def fake_scheduler(
        stop_event,
    ):
        await stop_event.wait()
        stopped.set()

    monkeypatch.setattr(
        main.database,
        "initialize_database",
        fake_initialize_database,
    )

    monkeypatch.setattr(
        main.scheduler,
        "run_retry_scheduler",
        fake_scheduler,
    )

    with TestClient(main.app):
        assert initialize_calls == [
            "initialized"
        ]

    assert stopped.wait(timeout=1)