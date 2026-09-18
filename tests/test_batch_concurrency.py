"""Verify bounded parallel batch submission and result ordering."""

import asyncio

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import flags as flags_api
from app.core.submitter import (
    SubmissionResult,
)


def make_flag(
    index: int,
) -> str:
    return (
        "FAUST_"
        + f"{index:032d}"
    )


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
        "Authorization": "Bearer test-token",
    }


def test_batch_uses_bounded_parallelism(
    monkeypatch,
):
    active = 0
    max_active = 0

    async def fake_submit(
        flag: str,
        host: str,
        port: int,
        timeout: float,
    ):
        nonlocal active
        nonlocal max_active

        active += 1

        max_active = max(
            max_active,
            active,
        )

        await asyncio.sleep(
            0.02
        )

        active -= 1

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

    flags = [
        make_flag(index)
        for index in range(24)
    ]

    response = client.post(
        "/api/flags/batch",
        headers=auth_headers(),
        json={
            "flags": flags,
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert (
        body["summary"]["accepted"]
        == 24
    )

    assert (
        max_active
        == flags_api.MAX_BATCH_CONCURRENCY
    )

    assert (
        max_active
        <= 8
    )


def test_parallel_batch_preserves_result_order(
    monkeypatch,
):
    async def fake_submit(
        flag: str,
        host: str,
        port: int,
        timeout: float,
    ):
        index = int(
            flag.removeprefix(
                "FAUST_"
            )
        )

        delay = (
            (20 - index)
            * 0.001
        )

        await asyncio.sleep(
            max(
                delay,
                0,
            )
        )

        return SubmissionResult(
            flag=flag,
            code="OK",
            message=f"accepted-{index}",
        )

    monkeypatch.setattr(
        flags_api,
        "submit_to_gameserver",
        fake_submit,
    )

    client = create_test_client(
        monkeypatch
    )

    flags = [
        make_flag(index)
        for index in range(20)
    ]

    response = client.post(
        "/api/flags/batch",
        headers=auth_headers(),
        json={
            "flags": flags,
        },
    )

    assert response.status_code == 200

    results = (
        response.json()[
            "results"
        ]
    )

    assert [
        result["index"]
        for result in results
    ] == list(
        range(20)
    )

    assert [
        result["message"]
        for result in results
    ] == [
        f"accepted-{index}"
        for index in range(20)
    ]
