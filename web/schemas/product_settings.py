from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Ds8SettingsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dynamic_ids: list[str] = Field(default_factory=list, max_length=1000)


class Ds9SettingsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tags: list[str] = Field(default_factory=list, max_length=200)


class Ds10SourceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str = Field(min_length=1, max_length=4096)


class AccountProxyRequest(BaseModel):
    """账号级 Proxy 修改请求。

    `proxy` 非空：设置/覆盖当前账号代理；`clear=true`：清除账号级覆盖并回退到
    BINGGO_PROXY / proxy.json。两者互斥，避免空字符串在 Web 上产生歧义。
    """

    model_config = ConfigDict(extra="forbid")

    proxy: str | None = Field(default=None, max_length=4096)
    clear: bool = False

    @model_validator(mode="after")
    def validate_operation(self) -> "AccountProxyRequest":
        value = str(self.proxy or "").strip()
        if self.clear and value:
            raise ValueError("proxy 与 clear=true 不能同时提供")
        if not self.clear and not value:
            raise ValueError("请输入代理地址，或使用 clear=true 清除账号级代理")
        return self
