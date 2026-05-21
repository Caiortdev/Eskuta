"""Testes do parser de argumentos do sidecar."""

from __future__ import annotations

import pytest

from app.main import _parse_args


def test_default_host_and_port() -> None:
    args = _parse_args([])
    assert args.host == "127.0.0.1"
    assert args.port == 8765


def test_override_port() -> None:
    args = _parse_args(["--port", "9999"])
    assert args.port == 9999


def test_override_host_explicit_loopback() -> None:
    args = _parse_args(["--host", "127.0.0.1"])
    assert args.host == "127.0.0.1"


def test_port_must_be_integer() -> None:
    with pytest.raises(SystemExit):
        _parse_args(["--port", "abc"])
