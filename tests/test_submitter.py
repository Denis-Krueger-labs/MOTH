import pytest

from app.core.submitter import parse_submission_response


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