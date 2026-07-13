from __future__ import annotations

import pytest

from src.participation import participate_activity
from src.sources.common import is_valid_dynamic_id


def test_participate_rejects_invalid_dynamic_id() -> None:
    class DummyClient:
        pass

    with pytest.raises(ValueError, match="dynamic_id"):
        participate_activity(DummyClient(), dynamic_id="bad", lottery_type="互动抽奖")


def test_is_valid_dynamic_id() -> None:
    assert is_valid_dynamic_id("1213708271262629897")
    assert not is_valid_dynamic_id("")
