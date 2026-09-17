from __future__ import annotations

import pytest
from helpers import EVENT_DATE

from pehchaan.domain.policy import EventPolicy


@pytest.fixture
def policy() -> EventPolicy:
    return EventPolicy(event_id="evt_test", event_date=EVENT_DATE, min_age=18)
