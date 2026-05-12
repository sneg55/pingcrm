"""Tests for app.core.version helpers."""
import importlib

from packaging.version import Version


def reload_version_module(monkeypatch, value: str | None):
    """Reload app.core.version with APP_VERSION set/unset for this test."""
    if value is None:
        monkeypatch.delenv("APP_VERSION", raising=False)
    else:
        monkeypatch.setenv("APP_VERSION", value)
    import app.core.version as v
    importlib.reload(v)
    return v


def test_app_version_defaults_to_dev(monkeypatch):
    v = reload_version_module(monkeypatch, None)
    assert v.APP_VERSION == "dev"
    assert v.is_semver_build() is False
    assert v.parse_current() is None


def test_app_version_reads_env(monkeypatch):
    v = reload_version_module(monkeypatch, "v1.6.0")
    assert v.APP_VERSION == "v1.6.0"
    assert v.is_semver_build() is True
    parsed = v.parse_current()
    assert parsed == Version("1.6.0")


def test_app_version_strips_v_prefix(monkeypatch):
    v = reload_version_module(monkeypatch, "1.6.0")
    assert v.is_semver_build() is True
    assert v.parse_current() == Version("1.6.0")


def test_app_version_rejects_sha(monkeypatch):
    v = reload_version_module(monkeypatch, "abc1234")
    assert v.is_semver_build() is False
    assert v.parse_current() is None


def test_app_version_handles_prerelease(monkeypatch):
    v = reload_version_module(monkeypatch, "v1.7.0-rc.1")
    assert v.is_semver_build() is True
    assert v.parse_current() == Version("1.7.0rc1")
