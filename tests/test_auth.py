from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import flags as flags_api


VALID_FLAG = "FAUST_" + ("A" * 32)


def create_test_client() -> TestClient:
    app = FastAPI()
    app.include_router(flags_api.router)

    return TestClient(app)


def test_mori_swats_visitor_without_authorization(
    monkeypatch,
):
    monkeypatch.setenv(
        "MOTH_API_TOKEN",
        "correct-token",
    )

    client = create_test_client()

    response = client.post(
        "/api/flags",
        json={
            "flag": VALID_FLAG,
        },
    )

    assert response.status_code == 401

    assert response.json() == {
        "detail": (
            "MORI found no authorization "
            "at the nest entrance"
        )
    }


def test_mori_swats_malformed_authorization(
    monkeypatch,
):
    monkeypatch.setenv(
        "MOTH_API_TOKEN",
        "correct-token",
    )

    client = create_test_client()

    response = client.post(
        "/api/flags",
        headers={
            "Authorization": "Moth correct-token",
        },
        json={
            "flag": VALID_FLAG,
        },
    )

    assert response.status_code == 401

    assert response.json() == {
        "detail": (
            "MORI swatted away malformed authorization"
        )
    }


def test_mori_swats_unknown_visitor(
    monkeypatch,
):
    monkeypatch.setenv(
        "MOTH_API_TOKEN",
        "correct-token",
    )

    client = create_test_client()

    response = client.post(
        "/api/flags",
        headers={
            "Authorization": "Bearer wrong-token",
        },
        json={
            "flag": VALID_FLAG,
        },
    )

    assert response.status_code == 401

    assert response.json() == {
        "detail": (
            "MORI does not recognize this visitor"
        )
    }


def test_mori_allows_known_visitor_into_the_nest(
    monkeypatch,
):
    monkeypatch.setenv(
        "MOTH_API_TOKEN",
        "correct-token",
    )

    monkeypatch.setattr(
        flags_api,
        "has_flag",
        lambda flag: True,
    )

    client = create_test_client()

    response = client.post(
        "/api/flags",
        headers={
            "Authorization": "Bearer correct-token",
        },
        json={
            "flag": VALID_FLAG,
        },
    )

    assert response.status_code == 200

    assert response.json() == {
        "status": "duplicate",
        "code": "LOCAL",
        "message": (
            "mof has already seen this offering"
        ),
        "remembered": True,
    }


def test_mori_swats_before_mof_checks_bad_flag(
    monkeypatch,
):
    monkeypatch.setenv(
        "MOTH_API_TOKEN",
        "correct-token",
    )

    client = create_test_client()

    response = client.post(
        "/api/flags",
        json={
            "flag": "definitely-not-a-flag",
        },
    )

    assert response.status_code == 401

    assert response.json() == {
        "detail": (
            "MORI found no authorization "
            "at the nest entrance"
        )
    }


def test_mori_refuses_unguarded_nest(
    monkeypatch,
):
    monkeypatch.delenv(
        "MOTH_API_TOKEN",
        raising=False,
    )

    client = create_test_client()

    response = client.post(
        "/api/flags",
        headers={
            "Authorization": "Bearer anything",
        },
        json={
            "flag": VALID_FLAG,
        },
    )

    assert response.status_code == 503

    assert response.json() == {
        "detail": (
            "MORI cannot guard the nest because "
            "MOTH_API_TOKEN is missing"
        )
    }