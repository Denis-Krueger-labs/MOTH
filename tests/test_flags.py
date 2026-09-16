import pytest
from pydantic import ValidationError

from app.api.flags import FlagSubmission


def test_mof_refuses_empty_flag():
    with pytest.raises(ValidationError):
        FlagSubmission(flag="     ")