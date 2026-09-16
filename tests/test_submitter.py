import pytest
import asyncio
from app.core.submitter import parse_submission_response
from app.core import submitter


def test_mof_understands_submission_response():
    result = parse_submission_response(
        "FAUST_TEST_MOF_123 OK accepted"
    )

    assert result.flag == "FAUST_TEST_MOF_123"
    assert result.code == "OK"
    assert result.message == "accepted"


def test_mof_refuses_broken_submission_response():
    with pytest.raises(ValueError):
        parse_submission_response("what even is this")


class FakeReader:
    async def readuntil(self, separator: bytes) -> bytes:
        assert separator == b"\n\n"
        return b"Welcome to fake moth gameserver\n\n"

    async def readline(self) -> bytes:
        return b"FAUST_TEST_MOF_123 OK accepted\n"


class FakeWriter:
    def __init__(self):
        self.data = b""
        self.closed = False

    def write(self, data: bytes) -> None:
        self.data += data

    async def drain(self) -> None:
        pass

    def close(self) -> None:
        self.closed = True

    async def wait_closed(self) -> None:
        pass


def test_mof_submits_flag_over_fake_tcp(monkeypatch):
    reader = FakeReader()
    writer = FakeWriter()

    async def fake_open_connection(host: str, port: int):
        assert host == "fake.gameserver"
        assert port == 666
        return reader, writer

    monkeypatch.setattr(
        submitter.asyncio,
        "open_connection",
        fake_open_connection,
    )

    result = asyncio.run(
        submitter.submit_flag(
            "FAUST_TEST_MOF_123",
            host="fake.gameserver",
            port=666,
        )
    )

    assert writer.data == b"FAUST_TEST_MOF_123\n"
    assert writer.closed is True

    assert result.flag == "FAUST_TEST_MOF_123"
    assert result.code == "OK"
    assert result.message == "accepted"