"""Blank environment variables must not crash Settings construction.

Docker Compose writes `TELEGRAM_API_ID: ${TELEGRAM_API_ID:-}` as an empty
string rather than omitting the variable, so every optional setting the user
left unconfigured arrives as "". That is fine for str fields but a hard
ValidationError for typed ones, which crashed startup in issue #149.
"""

import pytest

from app.core.config import Settings


def test_blank_int_env_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("TELEGRAM_API_ID", "")
    assert Settings(_env_file=None).TELEGRAM_API_ID == 0


def test_blank_bool_env_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("ALLOW_REGISTRATION", "")
    assert Settings(_env_file=None).ALLOW_REGISTRATION is False


def test_blank_list_env_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "")
    assert Settings(_env_file=None).CORS_ORIGINS == [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]


def test_blank_str_env_stays_blank(monkeypatch):
    monkeypatch.setenv("TELEGRAM_API_HASH", "")
    assert Settings(_env_file=None).TELEGRAM_API_HASH == ""


def test_populated_int_env_still_parsed(monkeypatch):
    monkeypatch.setenv("TELEGRAM_API_ID", "12345")
    assert Settings(_env_file=None).TELEGRAM_API_ID == 12345


def test_unparseable_int_env_still_raises(monkeypatch):
    monkeypatch.setenv("TELEGRAM_API_ID", "not-a-number")
    with pytest.raises(Exception):
        Settings(_env_file=None)
