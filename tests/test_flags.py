import pytest
from pydantic import ValidationError

from app.api.flags import FlagSubmission
from app.db.database import store_flag


def test_mof_refuses_empty_flag():
    with pytest.raises(ValidationError):
        FlagSubmission(flag="     ")


def test_mof_remembers_duplicate_flag(test_database):
    flag = "FAUST_TEST_DUPLICATE_123"

    first_offering = store_flag(flag)
    second_offering = store_flag(flag)

    assert first_offering is True
    assert second_offering is False

def test_mof_never_stores_plaintext(test_database):
    flag = "FAUST_SECRET_MOF_789"

    store_flag(flag)

    database_bytes = test_database.read_bytes()

    assert flag.encode("utf-8") not in database_bytes