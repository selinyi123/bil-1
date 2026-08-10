"""多账号池 + 代理配置测试。"""
from __future__ import annotations

from src import account_pool
from src import app_paths
from src.proxy_config import get_proxy_url

COOKIE_A = "SESSDATA=a1; bili_jct=jc1; DedeUserID=1001; DedeUserID__ckMd5=x"
COOKIE_B = "SESSDATA=b2; bili_jct=jc2; DedeUserID=1002; DedeUserID__ckMd5=y"


def test_register_login_cookie_materializes_active(isolated_home) -> None:
    uid = account_pool.register_login_cookie(COOKIE_A)
    assert uid == 1001
    assert account_pool.get_active_uid() == 1001
    # 活跃账号镜像到 cookies.txt
    materialized = app_paths.cookie_file().read_text(encoding="utf-8")
    assert "DedeUserID=1001" in materialized
    assert (app_paths.accounts_dir() / "1001.txt").exists()


def test_list_accounts_and_switch(isolated_home) -> None:
    account_pool.register_login_cookie(COOKIE_A)
    account_pool.register_login_cookie(COOKIE_B)

    accounts = account_pool.list_accounts()
    uids = sorted(item["uid"] for item in accounts)
    assert uids == [1001, 1002]
    active = [item for item in accounts if item["active"]]
    assert len(active) == 1 and active[0]["uid"] == 1002  # 最后登录者活跃

    # 切号到 1001：cookies.txt 内容切换
    assert account_pool.set_active(1001) is True
    assert account_pool.get_active_uid() == 1001
    materialized = app_paths.cookie_file().read_text(encoding="utf-8")
    assert "DedeUserID=1001" in materialized

    # 切换不存在的账号返回 False
    assert account_pool.set_active(9999) is False


def test_remove_account_clears_active(isolated_home) -> None:
    account_pool.register_login_cookie(COOKIE_A)
    account_pool.register_login_cookie(COOKIE_B)
    # 切到 1001 再删除它 → 活跃态清空
    account_pool.set_active(1001)
    assert account_pool.remove_account(1001) is True
    assert account_pool.get_active_uid() is None
    assert not app_paths.cookie_file().exists()
    # 池中仍保留 1002
    uids = sorted(item["uid"] for item in account_pool.list_accounts())
    assert uids == [1002]

    # 删除不存在账号返回 False
    assert account_pool.remove_account(9999) is False


def test_clear_active_keeps_pool(isolated_home) -> None:
    account_pool.register_login_cookie(COOKIE_A)
    account_pool.register_login_cookie(COOKIE_B)
    account_pool.clear_active()
    assert account_pool.get_active_uid() is None
    assert not app_paths.cookie_file().exists()
    uids = sorted(item["uid"] for item in account_pool.list_accounts())
    assert uids == [1001, 1002]


def test_list_accounts_adopts_legacy_cookie(isolated_home) -> None:
    """老版本单账号升级：ensure_legacy_account 把 cookies.txt 自动登记为账号。"""
    app_paths.cookie_file().parent.mkdir(parents=True, exist_ok=True)
    app_paths.cookie_file().write_text(COOKIE_A, encoding="utf-8")
    # list_accounts 本身纯读：池为空时先返回空
    assert account_pool.list_accounts() == []
    assert account_pool.ensure_legacy_account() == 1001
    accounts = account_pool.list_accounts()
    assert [item["uid"] for item in accounts] == [1001]
    assert account_pool.get_active_uid() == 1001
    # 幂等：再次调用不重复登记
    assert account_pool.ensure_legacy_account() is None


def test_register_login_cookie_rejects_no_uid(isolated_home) -> None:
    assert account_pool.register_login_cookie("SESSDATA=x; bili_jct=y") is None


def test_proxy_url_from_env(isolated_home, monkeypatch) -> None:
    monkeypatch.setenv("BINGGO_PROXY", "http://127.0.0.1:7890")
    assert get_proxy_url() == "http://127.0.0.1:7890"


def test_proxy_url_none_by_default(isolated_home, monkeypatch) -> None:
    monkeypatch.delenv("BINGGO_PROXY", raising=False)
    import src.proxy_config as proxy_config

    proxy_config._cache = {}
    assert get_proxy_url() is None
