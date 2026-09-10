from __future__ import annotations

from pydantic import BaseModel, ConfigDict, StrictBool


class AutoStartRequest(BaseModel):
    """启动定时调度器。

    `rotate_accounts` 只作用于本次运行，不持久化——调度器自身重启即停，
    开关比它活得久会造成"我以为没开轮转，一按启动就开始用多个号操作"。
    服务端可能拒绝（账号池不足 2 个 / `BILI_COOKIE` 覆盖身份），以回执为准。
    """

    model_config = ConfigDict(extra="forbid")

    rotate_accounts: StrictBool = False
