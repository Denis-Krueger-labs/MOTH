import asyncio

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.api import flags as flags_api
from app.api.flags import FlagSubmission
from app.core.submitter import (
    SubmissionConnectionError,
    SubmissionResult,
    SubmissionTimeoutError,
)
from app.db.database import has_flag, store_flag


VALID_FLAG = "FAUST_" + ("A" * 32)
SECOND_VALID_FLAG = "FAUST_" + ("B" * 32)
THIRD_VALID_FLAG = "FAUST_" + ("C" * 32)
FOURTH_VALID_FLAG = "FAUST_" + ("D" * 32)
FIFTH_VALID_FLAG = "FAUST_" + ("E" * 32)


def test_mof_refuses_empty_flag():
    with pytest.raises(ValidationError):
        FlagSubmission(
            flag="     ",
        )


def test_mof_accepts_real_faust_flag_shape():
    submission = FlagSubmission(
        flag=VALID_FLAG,
    )

    assert submission.flag == VALID_FLAG


def test_mof_refuses_short_fake_flag():
    with pytest.raises(
        ValidationError,
        match="does not recognize this as a FAUST flag",
    ):
        FlagSubmission(
            flag="FAUST_TOO_SHORT",
        )


def test_mof_refuses_wrong_flag_prefix():
    with pytest.raises(
        ValidationError,
        match="does not recognize this as a FAUST flag",
    ):
        FlagSubmission(
            flag="MOTH_" + ("A" * 32),
        )


def test_mof_refuses_invalid_flag_character():
    with pytest.raises(
        ValidationError,
        match="does not recognize this as a FAUST flag",
    ):
        FlagSubmission(
            flag="FAUST_" + ("A" * 31) + "!",
        )


def test_mof_remembers_duplicate_flag(
    test_database,
):
    flag = VALID_FLAG

    first_offering = store_flag(flag)
    second_offering = store_flag(flag)

    assert first_offering is True
    assert second_offering is False


def test_mof_knows_if_flag_was_seen(
    test_database,
):
    flag = SECOND_VALID_FLAG

    assert has_flag(flag) is False

    store_flag(flag)

    assert has_flag(flag) is True


def test_mof_never_stores_plaintext(
    test_database,
):
    flag = THIRD_VALID_FLAG

    store_flag(flag)

    database_bytes = test_database.read_bytes()

    assert flag.encode("utf-8") not in database_bytes


def test_mof_submits_new_flag_and_remembers_it(
    test_database,
    monkeypatch,
):
    flag = VALID_FLAG

    async def fake_submit(
        flag: str,
        host: str,
        port: int,
        timeout: float,
    ):
        assert host == "fake.gameserver"
        assert port == 666
        assert timeout == 2.0

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
    monkeypatch.setattr(
        flags_api,
        "get_submission_host",
        lambda: "fake.gameserver",
    )
    monkeypatch.setattr(
        flags_api,
        "get_submission_port",
        lambda: 666,
    )
    monkeypatch.setattr(
        flags_api,
        "get_submission_timeout",
        lambda: 2.0,
    )

    result = asyncio.run(
        flags_api.submit_flag(
            FlagSubmission(
                flag=flag,
            )
        )
    )

    assert result == {
        "status": "submitted",
        "code": "OK",
        "message": "accepted",
        "remembered": True,
    }

    assert has_flag(flag) is True


def test_mof_does_not_submit_local_duplicate(
    test_database,
    monkeypatch,
):
    flag = SECOND_VALID_FLAG

    store_flag(flag)

    async def fake_submit(
        flag: str,
        host: str,
        port: int,
        timeout: float,
    ):
        raise AssertionError(
            "mof should not submit a known flag"
        )

    monkeypatch.setattr(
        flags_api,
        "submit_to_gameserver",
        fake_submit,
    )

    result = asyncio.run(
        flags_api.submit_flag(
            FlagSubmission(
                flag=flag,
            )
        )
    )

    assert result["status"] == "duplicate"
    assert result["code"] == "LOCAL"
    assert result["remembered"] is True


def test_mof_does_not_remember_gameserver_error(
    test_database,
    monkeypatch,
):
    flag = THIRD_VALID_FLAG

    async def fake_submit(
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

    monkeypatch.setattr(
        flags_api,
        "submit_to_gameserver",
        fake_submit,
    )

    result = asyncio.run(
        flags_api.submit_flag(
            FlagSubmission(
                flag=flag,
            )
        )
    )

    assert result["code"] == "ERR"
    assert result["remembered"] is False
    assert has_flag(flag) is False


def test_mof_translates_silent_lamp_to_504(
    test_database,
    monkeypatch,
):
    flag = FOURTH_VALID_FLAG

    async def fake_submit(
        flag: str,
        host: str,
        port: int,
        timeout: float,
    ):
        raise SubmissionTimeoutError(
            "mof waited for the lämp, but it never answered"
        )

    monkeypatch.setattr(
        flags_api,
        "submit_to_gameserver",
        fake_submit,
    )

    with pytest.raises(HTTPException) as error:
        asyncio.run(
            flags_api.submit_flag(
                FlagSubmission(
                    flag=flag,
                )
            )
        )

    assert error.value.status_code == 504
    assert has_flag(flag) is False


def test_mof_translates_missing_lamp_to_502(
    test_database,
    monkeypatch,
):
    flag = FIFTH_VALID_FLAG

    async def fake_submit(
        flag: str,
        host: str,
        port: int,
        timeout: float,
    ):
        raise SubmissionConnectionError(
            "mof could not find the lämp"
        )

    monkeypatch.setattr(
        flags_api,
        "submit_to_gameserver",
        fake_submit,
    )

    with pytest.raises(HTTPException) as error:
        asyncio.run(
            flags_api.submit_flag(
                FlagSubmission(
                    flag=flag,
                )
            )
        )

    assert error.value.status_code == 502
    assert has_flag(flag) is False