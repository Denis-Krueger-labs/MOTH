import asyncio

from fastapi.testclient import TestClient

from app import main
from app.api import dashboard as dashboard_api
from app.core import operational_health
from app.db import database


FIRST_FLAG = "FAUST_" + ("P" * 32)


def _auth_headers(
    monkeypatch,
) -> dict[str, str]:
    token = "test-moth-token"

    monkeypatch.setenv(
        "MOTH_API_TOKEN",
        token,
    )

    return {
        "Authorization": (
            f"Bearer {token}"
        ),
    }


def test_dashboard_health_reports_running_scheduler(
    test_database,
    monkeypatch,
):
    headers = _auth_headers(
        monkeypatch
    )

    with TestClient(
        main.app
    ) as client:
        response = client.get(
            "/api/dashboard/health",
            headers=headers,
        )

    assert response.status_code == 200

    body = response.json()

    assert body["status"] == "healthy"

    assert (
        body["scheduler"]["state"]
        == "running"
    )

    assert (
        body["scheduler"]["running"]
        is True
    )

    assert (
        body["retry_queue"]["state"]
        == "clear"
    )

    assert (
        body["retry_queue"]["retryable"]
        == 0
    )


def test_dashboard_health_reports_waiting_retry_queue(
    test_database,
    monkeypatch,
):
    database.record_submission(
        FIRST_FLAG,
        state=database.RETRYABLE_STATE,
        response_code="ERR",
        response_message=(
            "try again later"
        ),
    )

    headers = _auth_headers(
        monkeypatch
    )

    with TestClient(
        main.app
    ) as client:
        response = client.get(
            "/api/dashboard/health",
            headers=headers,
        )

    assert response.status_code == 200

    queue = response.json()[
        "retry_queue"
    ]

    assert queue["retryable"] == 1

    assert queue["state"] == "waiting"


def test_connectivity_probe_reads_greeting_without_sending(
    test_database,
    monkeypatch,
):
    class FakeReader:
        async def readuntil(
            self,
            separator: bytes,
        ) -> bytes:
            assert separator == b"\n\n"

            return (
                b"hello little moth\n\n"
            )

    class FakeWriter:
        def __init__(self):
            self.closed = False

        def write(
            self,
            data: bytes,
        ) -> None:
            raise AssertionError(
                "connectivity probe "
                "must never send data"
            )

        def close(self) -> None:
            self.closed = True

        async def wait_closed(
            self,
        ) -> None:
            return None

    writer = FakeWriter()

    async def fake_open_connection(
        host: str,
        port: int,
    ):
        assert host == "127.0.0.1"
        assert port == 6666

        return (
            FakeReader(),
            writer,
        )

    monkeypatch.setattr(
        operational_health.asyncio,
        "open_connection",
        fake_open_connection,
    )

    result = asyncio.run(
        operational_health
        .probe_submission_server()
    )

    assert result["status"] == "reachable"
    assert result["reachable"] is True

    assert (
        result["greeting_received"]
        is True
    )

    assert result["greeting_bytes"] > 0
    assert writer.closed is True


def test_connectivity_probe_handles_unreachable_server(
    test_database,
    monkeypatch,
):
    async def fake_open_connection(
        host: str,
        port: int,
    ):
        raise ConnectionRefusedError(
            "no lämp"
        )

    monkeypatch.setattr(
        operational_health.asyncio,
        "open_connection",
        fake_open_connection,
    )

    result = asyncio.run(
        operational_health
        .probe_submission_server()
    )

    assert (
        result["status"]
        == "unreachable"
    )

    assert result["reachable"] is False

    assert (
        result["greeting_received"]
        is False
    )


def test_connectivity_endpoint_returns_probe_result(
    test_database,
    monkeypatch,
):
    async def fake_probe():
        return {
            "status": "reachable",
            "reachable": True,
            "host": "127.0.0.1",
            "port": 6666,
            "latency_ms": 4.2,
            "greeting_received": True,
            "greeting_bytes": 42,
        }

    monkeypatch.setattr(
        dashboard_api,
        "probe_submission_server",
        fake_probe,
    )

    headers = _auth_headers(
        monkeypatch
    )

    with TestClient(
        main.app
    ) as client:
        response = client.get(
            "/api/dashboard/connectivity",
            headers=headers,
        )

    assert response.status_code == 200

    body = response.json()

    assert body["status"] == "reachable"
    assert body["reachable"] is True

    assert (
        body["greeting_received"]
        is True
    )