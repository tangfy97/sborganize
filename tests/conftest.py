import pytest

from sborganize.cli import demo_layout


@pytest.fixture
def layout():
    return demo_layout()
