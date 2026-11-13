"""Shared pytest fixtures. Puts Project_4 on sys.path so `fleetkit` and `fleetopt` import."""

import sys
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from fleetkit import Instance, load_instance  # noqa: E402


@pytest.fixture(scope="session")
def inst() -> Instance:
    return load_instance(data_dir=PROJECT / "data")


@pytest.fixture(scope="session")
def project() -> Path:
    return PROJECT
