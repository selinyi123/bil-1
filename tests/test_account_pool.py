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


def test_ensure_legacy_account_skipped_under_env_cookie(isolated_home, monkeypatch) -> None:
    """BILI_COOKIE env 生效时不收养 cookies.txt 影子身份（登记了也无法使用）。"""
    app_paths.cookie_file().parent.mkdir(parents=True, exist_ok=True)
    app_paths.cookie_file().write_text(COOKIE_A, encoding="utf-8")
    monkeypatch.setenv("BILI_COOKIE", COOKIE_B)
    assert account_pool.ensure_legacy_account() is None
    assert account_pool.list_accounts() == []  # 未登记任何账号
    assert account_pool.get_active_uid() == 1002  # 身份仍由 env 决定


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


# ----------------------------------------------------------------------
# P1 #3 身份统一解析：BILI_COOKIE env > 账号池活跃账号 > cookies.txt
# ----------------------------------------------------------------------


def test_effective_uid_env_overrides_active_and_switch_rejected(isolated_home, monkeypatch) -> None:
    """env BILI_COOKIE=1001 + 账号池 active=1002 → 生效身份=1001，切换被拒绝。"""
    from src.bilibili_auth import resolve_effective_uid
    from src.user_data import get_active_uid as user_data_active_uid

    account_pool.register_login_cookie(COOKIE_B)  # active 文件 = 1002
    monkeypatch.setenv("BILI_COOKIE", COOKIE_A)  # env uid = 1001

    # UI 侧（account_pool）与业务侧（user_data）都解析为 env 身份，与实际请求一致
    assert account_pool.get_active_uid() == 1001
    assert user_data_active_uid() == 1001
    assert resolve_effective_uid() == 1001

    # set_active 被 env 拒绝：返回 False，active 文件与 cookies.txt 均不被改写
    assert account_pool.set_active(1002) is False
    assert account_pool.get_active_uid() == 1001
    assert (app_paths.accounts_dir() / "active").read_text(encoding="utf-8").strip() == "1002"
    assert "DedeUserID=1002" in app_paths.cookie_file().read_text(encoding="utf-8")

    # 账号列表的 active 标记与生效身份一致（env uid 不在池中 → 无账号标记 active）
    assert all(not item["active"] for item in account_pool.list_accounts())


def test_effective_uid_env_priority_chain(isolated_home, monkeypatch) -> None:
    """无 env：active 文件优先；无 active 文件：cookies.txt（legacy）兜底。"""
    from src.bilibili_auth import resolve_effective_uid

    monkeypatch.delenv("BILI_COOKIE", raising=False)
    account_pool.register_login_cookie(COOKIE_A)
    assert account_pool.get_active_uid() == 1001  # pool active

    # 移除 active 文件但保留 cookies.txt（镜像仍在）→ 退回 cookies.txt 解析
    (app_paths.accounts_dir() / "active").unlink()
    assert resolve_effective_uid() == 1001


def test_register_login_cookie_env_mode_registers_without_switching(isolated_home, monkeypatch) -> None:
    """env 生效时扫码登录：账号仅登记，不切换活跃、不镜像 cookies.txt。"""
    monkeypatch.setenv("BILI_COOKIE", COOKIE_A)
    uid = account_pool.register_login_cookie(COOKIE_B)
    assert uid == 1002  # 登记成功
    assert (app_paths.accounts_dir() / "1002.txt").exists()
    assert not (app_paths.accounts_dir() / "active").exists()  # 未切换活跃
    assert not app_paths.cookie_file().exists()  # 未镜像
    assert account_pool.get_active_uid() == 1001  # 身份仍为 env


# ----------------------------------------------------------------------
# P1 #15 账号级代理
# ----------------------------------------------------------------------


def test_account_proxy_roundtrip_and_priority(isolated_home, monkeypatch) -> None:
    monkeypatch.delenv("BINGGO_PROXY", raising=False)
    account_pool.register_login_cookie(COOKIE_A)

    # 未配置账号级代理 → None；不存在的账号无法设置
    assert get_proxy_url(uid=1001) is None
    assert account_pool.set_account_proxy(9999, "http://127.0.0.1:9") is False

    # 设置账号级代理后生效；不带 uid 调用不读账号级（向后兼容）
    assert account_pool.set_account_proxy(1001, "http://127.0.0.1:1080") is True
    assert get_proxy_url(uid=1001) == "http://127.0.0.1:1080"
    assert get_proxy_url() is None

    # env 显式注入最高优先级
    monkeypatch.setenv("BINGGO_PROXY", "http://127.0.0.1:7890")
    assert get_proxy_url(uid=1001) == "http://127.0.0.1:7890"

    # 清除账号级代理（env 仍生效时返回 env 值）
    assert account_pool.set_account_proxy(1001, None) is True
    assert get_proxy_url(uid=1001) == "http://127.0.0.1:7890"
    # 清除 env 后：账号级已清除 → None
    monkeypatch.delenv("BINGGO_PROXY", raising=False)
    assert get_proxy_url(uid=1001) is None


def test_proxy_json_hot_reload(isolated_home, monkeypatch) -> None:
    import time

    monkeypatch.delenv("BINGGO_PROXY", raising=False)
    import src.proxy_config as proxy_config

    proxy_config._cache = None
    proxy_config._cache_path = None
    proxy_config._cache_mtime = None

    path = app_paths.config_dir() / "proxy.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"url": "http://127.0.0.1:1111"}', encoding="utf-8")
    assert get_proxy_url() == "http://127.0.0.1:1111"

    time.sleep(0.02)  # 保证 mtime 变化
    path.write_text('{"url": "http://127.0.0.1:2222"}', encoding="utf-8")
    assert get_proxy_url() == "http://127.0.0.1:2222"  # 无需重启即热更新

    path.unlink()
    assert get_proxy_url() is None
