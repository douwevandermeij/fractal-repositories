from datetime import datetime, timezone

import pytest


@pytest.fixture
def now():
    return datetime.now(timezone.utc)
