"""Verify bounded concurrent submission capacity and overload responses."""

import threading
from concurrent.futures import (
    ThreadPoolExecutor,
)

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import flags as flags_api
from app.core.submission_capacity import (
    SubmissionCapacity,
)
from app.core.submitter import (
    SubmissionResult,
)
from app.db.submission_gate import (
    claim_initial_submission,
    release_initial_submission,
)


FIRST_FLAG = "FAUST_" + ("S" * 32)
SECOND_FLAG = "FAUST_" + ("T" * 32)


def create_test_client(
    monkeypatch,
) -> TestClient:
    monkeypatch.setenv(
        "MOTH_API_TOKEN",
        "test-token",
    )

    app = FastAPI()
    app.include_router(
        flags_api.router
    )

    return TestClient(app)


def auth_headers() -> dict[str, str]:
    return {
        "Authorization": (
            "Bearer test-token"
        ),
    }


def test_capacity_rejects_after_limit_and_recovers():
    capacity = SubmissionCapacity(
        limit=2
    )

    assert (
        capacity.try_acquire()
        is True
    )

    assert (
        capacity.try_acquire()
        is True
    )

    assert capacity.active == 2

    assert (
        capacity.try_acquire()
        is False
    )

    capacity.release()

    assert capacity.active == 1

    assert (
        capacity.try_acquire()
        is True
    )

    assert capacity.active == 2


def test_capacity_is_safe_under_concurrent_acquisition():
    limit = 16
    workers = 64

    capacity = SubmissionCapacity(
        limit=limit
    )

    barrier = threading.Barrier(
        workers
    )

    def attempt(
        _: int,
    ) -> bool:
        barrier.wait()

        return (
            capacity.try_acquire()
        )

    with ThreadPoolExecutor(
        max_workers=workers
    ) as pool:
        results = list(
            pool.map(
                attempt,
                range(workers),
            )
        )

    assert sum(results) == limit
    assert capacity.active == limit

    for _ in range(limit):
        capacity.release()

    assert capacity.active == 0


def test_single_submission_returns_503_when_capacity_is_full(
    monkeypatch,
):
    capacity = SubmissionCapacity(
        limit=1
    )

    assert capacity.try_acquire()

    monkeypatch.setattr(
        flags_api,
        "submission_capacity",
        capacity,
    )

    async def forbidden_submit(
        flag: str,
        host: str,
        port: int,
        timeout: float,
    ):
        raise AssertionError(
            "overloaded submission "
            "must not reach gameserver"
        )

    monkeypatch.setattr(
        flags_api,
        "submit_to_gameserver",
        forbidden_submit,
    )

    client = create_test_client(
        monkeypatch
    )

    response = client.post(
        "/api/flags",
        headers=auth_headers(),
        json={
            "flag": FIRST_FLAG,
        },
    )

    assert response.status_code == 503

    assert (
        response.headers[
            "Retry-After"
        ]
        == "1"
    )

    assert response.json() == {
        "detail": (
            "MORI refuses another submission "
            "until the nest has capacity"
        )
    }

    claim = claim_initial_submission(
        FIRST_FLAG,
        "recovery-worker",
    )

    assert claim.status == "claimed"
    assert claim.lease_token is not None

    release_initial_submission(
        FIRST_FLAG,
        "recovery-worker",
        claim.lease_token,
    )


def test_batch_counts_overload_separately(
    monkeypatch,
):
    capacity = SubmissionCapacity(
        limit=1
    )

    assert capacity.try_acquire()

    monkeypatch.setattr(
        flags_api,
        "submission_capacity",
        capacity,
    )

    async def forbidden_submit(
        flag: str,
        host: str,
        port: int,
        timeout: float,
    ):
        raise AssertionError(
            "overloaded batch item "
            "must not reach gameserver"
        )

    monkeypatch.setattr(
        flags_api,
        "submit_to_gameserver",
        forbidden_submit,
    )

    client = create_test_client(
        monkeypatch
    )

    response = client.post(
        "/api/flags/batch",
        headers=auth_headers(),
        json={
            "flags": [
                FIRST_FLAG,
            ],
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["summary"] == {
        "received": 1,
        "accepted": 0,
        "duplicate": 0,
        "terminal_other": 0,
        "retryable": 0,
        "invalid": 0,
        "in_flight": 0,
        "overloaded": 1,
    }

    result = body["results"][0]

    assert (
        result["status"]
        == "overloaded"
    )

    assert (
        result["code"]
        == "OVERLOADED"
    )


def test_successful_submission_releases_capacity(
    monkeypatch,
):
    capacity = SubmissionCapacity(
        limit=1
    )

    monkeypatch.setattr(
        flags_api,
        "submission_capacity",
        capacity,
    )

    async def fake_submit(
        flag: str,
        host: str,
        port: int,
        timeout: float,
    ):
        return SubmissionResult(
            flag=flag,
            code="OK",
            message="accepted",
        )

    monkeypatch.setattr(
        flags_api,
        "submit_to_gameserver",
        fake_submit,
    )

    client = create_test_client(
        monkeypatch
    )

    first = client.post(
        "/api/flags",
        headers=auth_headers(),
        json={
            "flag": FIRST_FLAG,
        },
    )

    assert first.status_code == 200
    assert capacity.active == 0

    second = client.post(
        "/api/flags",
        headers=auth_headers(),
        json={
            "flag": SECOND_FLAG,
        },
    )

    assert second.status_code == 200
    assert capacity.active == 0
