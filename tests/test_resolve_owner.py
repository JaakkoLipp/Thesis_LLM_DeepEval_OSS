"""Tests for resolve_owner_id in service.py."""
from __future__ import annotations

from deepeval_mvp.service import resolve_owner_id


def test_explicit_owner_id(monkeypatch):
    monkeypatch.setenv("OWNER_ID", "custom-owner-123")
    assert resolve_owner_id() == "custom-owner-123"


def test_pod_name_used_when_no_explicit_owner(monkeypatch):
    monkeypatch.delenv("OWNER_ID", raising=False)
    monkeypatch.setenv("POD_NAME", "eval-pod-abc")
    monkeypatch.delenv("HOSTNAME", raising=False)

    owner = resolve_owner_id()
    assert owner.startswith("eval-pod-abc:")
    # Format: host:pid:uuid_hex8
    parts = owner.split(":")
    assert len(parts) == 3
    assert parts[0] == "eval-pod-abc"
    assert parts[1].isdigit()
    assert len(parts[2]) == 8


def test_hostname_fallback(monkeypatch):
    monkeypatch.delenv("OWNER_ID", raising=False)
    monkeypatch.delenv("POD_NAME", raising=False)
    monkeypatch.setenv("HOSTNAME", "myhost")

    owner = resolve_owner_id()
    assert owner.startswith("myhost:")


def test_auto_derived_format(monkeypatch):
    monkeypatch.delenv("OWNER_ID", raising=False)
    monkeypatch.delenv("POD_NAME", raising=False)
    monkeypatch.delenv("HOSTNAME", raising=False)

    owner = resolve_owner_id()
    parts = owner.split(":")
    assert len(parts) == 3
    assert parts[1].isdigit()
    assert len(parts[2]) == 8
