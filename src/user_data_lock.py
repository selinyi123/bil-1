from __future__ import annotations

import threading

_user_data_lock = threading.RLock()


def user_data_lock() -> threading.Lock:
    return _user_data_lock
