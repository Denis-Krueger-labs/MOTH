"""Verify conversion of game-server responses and failures into outcomes."""

import asyncio

from app.core.submission_service import (
    submit_once,
)
from app.core.submitter import (
    SubmissionConnectionError,
    SubmissionResult,
    SubmissionTimeoutError,
)


FLAG = "FAUST_" + ("Q" * 32)


def test_submission_service_marks_ok_terminal():
    async def fake_submitter(
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

    outcome = asyncio.run(
        submit_once(
            FLAG,
            submitter=fake_submitter,
        )
    )

    assert outcome.code == "OK"
    assert outcome.message == "accepted"
    assert outcome.terminal is True


def test_submission_service_marks_err_retryable():
    async def fake_submitter(
        flag: str,
        host: str,
        port: int,
        timeout: float,
    ):
        return SubmissionResult(
            flag=flag,
            code="ERR",
            message="try again later",
        )

    outcome = asyncio.run(
        submit_once(
            FLAG,
            submitter=fake_submitter,
        )
    )

    assert outcome.code == "ERR"
    assert outcome.message == "try again later"
    assert outcome.terminal is False


def test_submission_service_converts_timeout():
    async def fake_submitter(
        flag: str,
        host: str,
        port: int,
        timeout: float,
    ):
        raise SubmissionTimeoutError(
            "mof waited for the lämp"
        )

    outcome = asyncio.run(
        submit_once(
            FLAG,
            submitter=fake_submitter,
        )
    )

    assert outcome.code == "TIMEOUT"

    assert (
        outcome.message
        == "mof waited for the lämp"
    )

    assert outcome.terminal is False


def test_submission_service_converts_connection_error():
    async def fake_submitter(
        flag: str,
        host: str,
        port: int,
        timeout: float,
    ):
        raise SubmissionConnectionError(
            "mof could not find the lämp"
        )

    outcome = asyncio.run(
        submit_once(
            FLAG,
            submitter=fake_submitter,
        )
    )

    assert (
        outcome.code
        == "CONNECTION_ERROR"
    )

    assert (
        outcome.message
        == "mof could not find the lämp"
    )

    assert outcome.terminal is False


def test_submission_service_converts_protocol_error():
    async def fake_submitter(
        flag: str,
        host: str,
        port: int,
        timeout: float,
    ):
        raise ValueError(
            "gameserver spoke forbidden moth"
        )

    outcome = asyncio.run(
        submit_once(
            FLAG,
            submitter=fake_submitter,
        )
    )

    assert (
        outcome.code
        == "PROTOCOL_ERROR"
    )

    assert (
        outcome.message
        == "gameserver spoke forbidden moth"
    )

    assert outcome.terminal is False
