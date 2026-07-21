"""Binggo MCP stdio server — thin wrapper over http://127.0.0.1:8787.

Does not import or modify the main Binggo application packages.
"""

from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.utilities.types import Image

from binggo_mcp.client import BinggoApiError, BinggoClient, as_tool_text
from binggo_mcp.instructions import INSTRUCTIONS
from binggo_mcp.jobs import (
    cancel_login_only,
    get_current_job,
    run_job_to_terminal,
    start_login_until_qrcode,
)
from binggo_mcp.serial import with_serial_lock

mcp = FastMCP(
    "binggo",
    instructions=INSTRUCTIONS,
)

_client: BinggoClient | None = None


def _api() -> BinggoClient:
    global _client
    if _client is None:
        _client = BinggoClient()
    return _client


def _err(exc: Exception) -> str:
    if isinstance(exc, BinggoApiError):
        return str(exc)
    return f"MCP 内部错误：{exc}"


# ----- Read tools -----


@mcp.tool()
@with_serial_lock
async def account_get(include_extras: bool = True) -> str:
    """读取账号卡片摘要（对应网页侧栏/概览账号区）。

    返回登录态、昵称、网络异常提示等。默认附带 extras。
    写操作前建议先调用；未登录时引导 account_login，不要臆造已登录。
    """
    try:
        client = _api()
        account = await client.get_json("/api/account")
        payload: dict[str, Any] = {"account": account}
        if include_extras:
            try:
                payload["extras"] = await client.get_json("/api/account/extras")
            except BinggoApiError as exc:
                payload["extras_error"] = str(exc)
        return as_tool_text(payload)
    except Exception as exc:
        return _err(exc)


@mcp.tool()
@with_serial_lock
async def summary_get() -> str:
    """读取概览统计与数据源/监控摘要（对应网页概览）。

    含活动统计、源状态摘要，以及当前 job 快照。适合开场了解全局状态。
    """
    try:
        return as_tool_text(await _api().get_json("/api/summary"))
    except Exception as exc:
        return _err(exc)


@mcp.tool()
@with_serial_lock
async def settings_get() -> str:
    """读取参与文案等设置（对应网页参与文案面板）。

    含模式、当前文案、默认文案字段。改文案前先读此工具了解当前 mode。
    """
    try:
        return as_tool_text(await _api().get_json("/api/settings"))
    except Exception as exc:
        return _err(exc)


@mcp.tool()
@with_serial_lock
async def llm_settings_get() -> str:
    """读取 LLM 配置摘要（对应网页 LLM 面板）。

    密钥已脱敏，仅有是否配置、是否测试通过、模型名等。禁止向用户索要或回显明文 Key。
    """
    try:
        return as_tool_text(await _api().get_json("/api/settings/llm"))
    except Exception as exc:
        return _err(exc)


@mcp.tool()
@with_serial_lock
async def runtime_get() -> str:
    """读取运行时/项目信息（对应网页 bilibinggo 项目信息区）。

    含版本、数据目录、runtime 标签等。
    """
    try:
        return as_tool_text(await _api().get_json("/api/runtime"))
    except Exception as exc:
        return _err(exc)


@mcp.tool()
@with_serial_lock
async def watch_users_list() -> str:
    """读取监控用户名单与同步状态（对应网页监控名单/同步卡片）。

    添加或删除用户前先读此列表；更新动态用 job_refresh_watch。
    """
    try:
        return as_tool_text(await _api().get_json("/api/watch-users"))
    except Exception as exc:
        return _err(exc)


@mcp.tool()
@with_serial_lock
async def activities_list(
    status: str | None = None,
    type: str | None = None,
    draw: str | None = None,
    draw_window: str | None = None,
    q: str | None = None,
    sort: str | None = None,
    order: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> str:
    """读取活动列表（对应网页活动表；筛选参数与网页 query 一致）。

    单条参与前用本工具拿到 dynamic_id，再调 job_participate。
    page/page_size 用于分页；q 为搜索关键字。
    """
    try:
        return as_tool_text(
            await _api().get_json(
                "/api/activities",
                params={
                    "status": status,
                    "type": type,
                    "draw": draw,
                    "draw_window": draw_window,
                    "q": q,
                    "sort": sort,
                    "order": order,
                    "page": page,
                    "page_size": page_size,
                },
            )
        )
    except Exception as exc:
        return _err(exc)


@mcp.tool()
@with_serial_lock
async def triple_targets_get(
    status: str | None = None,
    type: str | None = None,
    draw: str | None = None,
    draw_window: str | None = None,
    q: str | None = None,
    sort: str | None = None,
    order: str | None = None,
) -> str:
    """读取三连参与目标预览（对应活动页三连目标条）。

    调用 job_participate_triple 前可用本工具确认将参与哪些目标。
    """
    try:
        return as_tool_text(
            await _api().get_json(
                "/api/activities/triple-targets",
                params={
                    "status": status,
                    "type": type,
                    "draw": draw,
                    "draw_window": draw_window,
                    "q": q,
                    "sort": sort,
                    "order": order,
                },
            )
        )
    except Exception as exc:
        return _err(exc)


@mcp.tool()
@with_serial_lock
async def job_get() -> str:
    """读取当前 Job 状态/进度/结果（对应顶部进度条与结果横幅）。

    登录流程中串行轮询本工具查看 login_phase 与 state。
    其它 job_* 工具会等到终态才返回，一般不必中途轮询；若需看日志用 job_logs_get。
    """
    try:
        return as_tool_text(await get_current_job(_api()))
    except Exception as exc:
        return _err(exc)


@mcp.tool()
@with_serial_lock
async def job_logs_get(job_id: int | None = None, limit: int = 200) -> str:
    """读取任务日志摘要（对应网页任务日志坞）。

    可选 job_id；默认最近日志。limit 默认 200。
    """
    try:
        return as_tool_text(
            await _api().get_json(
                "/api/diagnostics/logs",
                params={"job_id": job_id, "limit": limit},
            )
        )
    except Exception as exc:
        return _err(exc)


@mcp.tool()
@with_serial_lock
async def auto_status_get() -> str:
    """读取定时点击调度器状态（对应定时点击坞）。

    启动/停止调度前先读相位、倒计时、fatal 原因等。
    """
    try:
        return as_tool_text(await _api().get_json("/api/auto/status"))
    except Exception as exc:
        return _err(exc)


@mcp.tool()
@with_serial_lock
async def account_login_qrcode() -> list[Any]:
    """获取当前登录二维码 PNG（对应扫码弹窗中的图）。

    须已在登录流程中（通常先 account_login）。返回图片 + 简短 job 元数据。
    二维码刷新后再次调用本工具取新图并展示给用户。码尚未生成时会报错。
    """
    try:
        job = await get_current_job(_api())
        png = await _api().get_bytes("/api/login/qrcode")
        meta = {
            "message": "请使用哔哩哔哩 App 扫码",
            "job": {
                "state": job.get("state"),
                "action": job.get("action"),
                "message": job.get("message"),
                "result": job.get("result"),
            },
        }
        return [Image(data=png, format="png"), as_tool_text(meta)]
    except Exception as exc:
        return [_err(exc)]


# ----- Account actions -----


@mcp.tool()
@with_serial_lock
async def account_login() -> list[Any]:
    """扫码登录（对应侧栏「扫码登录」/重新扫码）。

    二维码就绪后返回 PNG 图片；登录 Job 仍在服务端继续。
    必须把图片展示给用户扫码，然后串行轮询 job_get 直至 success/error。
    换码用 account_login_qrcode；放弃用 account_login_cancel。
    已登录时勿盲目调用，除非用户明确要求重登。
    """
    try:
        job, png = await start_login_until_qrcode(_api())
        meta = {
            "message": (
                "二维码已生成，请扫码并在手机上确认。"
                "登录任务仍在进行：请串行调用 job_get 查看 login_phase；"
                "若二维码刷新请调用 account_login_qrcode；"
                "取消请调用 account_login_cancel（等同关闭扫码弹窗）。"
            ),
            "job": job,
        }
        return [Image(data=png, format="png"), as_tool_text(meta)]
    except Exception as exc:
        return [_err(exc)]


@mcp.tool()
@with_serial_lock
async def account_login_cancel() -> str:
    """关闭扫码/取消进行中的登录（对应扫码弹窗 ×）。

    仅当当前 Job 为 login 时有效。这不是通用「取消任务」按钮，不能取消抽奖/更新类 Job。
    """
    try:
        return as_tool_text(await cancel_login_only(_api()))
    except Exception as exc:
        return _err(exc)


@mcp.tool()
@with_serial_lock
async def account_refresh(include_extras: bool = True) -> str:
    """刷新账号（对应侧栏「刷新账号」）。

    仅重新拉取账号接口，不是重新扫码。网络异常恢复后可用；Cookie 失效应走 account_login。
    """
    try:
        client = _api()
        account = await client.get_json("/api/account")
        payload: dict[str, Any] = {"account": account}
        if include_extras:
            try:
                payload["extras"] = await client.get_json("/api/account/extras")
            except BinggoApiError as exc:
                payload["extras_error"] = str(exc)
        return as_tool_text(payload)
    except Exception as exc:
        return _err(exc)


@mcp.tool()
@with_serial_lock
async def account_logout() -> str:
    """退出登录（对应侧栏「退出登录」）。

    清除本机登录态；响应不含 Cookie。退出后需登录的写操作会失败，应再走 account_login。
    """
    try:
        return as_tool_text(await _api().post_json("/api/logout"))
    except Exception as exc:
        return _err(exc)


@mcp.tool()
@with_serial_lock
async def account_ack_at_unread(current: int) -> str:
    """确认 @ 未读提示（对应账号区「知道了」）。

    current 为当前未读数（与网页一致）。用于消除「@我的未读增加」提示。
    """
    try:
        return as_tool_text(
            await _api().post_json(
                "/api/account/ack-at-unread",
                json_body={"current": int(current)},
            )
        )
    except Exception as exc:
        return _err(exc)


# ----- Job actions (wait until terminal) -----


@mcp.tool()
@with_serial_lock
async def job_refresh_watch() -> str:
    """更新监控用户动态（对应网页「更新监控用户动态」）。

    会阻塞直到任务终态再返回。需已登录；日常同步监控源用此工具。
    """
    try:
        return as_tool_text(await run_job_to_terminal(_api(), "refresh_watch"))
    except Exception as exc:
        return _err(exc)


@mcp.tool()
@with_serial_lock
async def job_refresh_status() -> str:
    """刷新任务状态（对应网页「刷新任务状态」）。

    会阻塞直到任务终态再返回。用于刷新活动开奖/参与状态等。
    """
    try:
        return as_tool_text(await run_job_to_terminal(_api(), "refresh_status"))
    except Exception as exc:
        return _err(exc)


@mcp.tool()
@with_serial_lock
async def job_refresh_all() -> str:
    """一键更新活动链接（对应网页「一键更新」）。

    会阻塞直到终态；耗时可能很长，且更易触发风控。仅在用户明确要求一键全量更新时使用；
    日常优先 job_refresh_source 单源更新。
    """
    try:
        return as_tool_text(await run_job_to_terminal(_api(), "refresh_all"))
    except Exception as exc:
        return _err(exc)


@mcp.tool()
@with_serial_lock
async def job_refresh_source(source_id: str) -> str:
    """更新此源/UP 合集（对应网页各源「更新此源」）。

    参数 source_id 须为有效数据源 ID。会阻塞直到终态。推荐的日常更新方式。
    """
    try:
        return as_tool_text(
            await run_job_to_terminal(
                _api(),
                "refresh_source",
                {"source_id": str(source_id).strip()},
            )
        )
    except Exception as exc:
        return _err(exc)


@mcp.tool()
@with_serial_lock
async def job_participate(dynamic_id: str) -> str:
    """单条参与抽奖（对应活动行「参与」按钮）。

    参数 dynamic_id 来自 activities_list。会阻塞直到终态。需已登录且 LLM 等前置满足网页同等要求。
    """
    try:
        return as_tool_text(
            await run_job_to_terminal(
                _api(),
                "participate",
                {"dynamic_id": str(dynamic_id).strip()},
            )
        )
    except Exception as exc:
        return _err(exc)


@mcp.tool()
@with_serial_lock
async def job_participate_triple() -> str:
    """三连参与（对应活动页顶部三连参与）。

    会阻塞直到终态。调用前可用 triple_targets_get 预览目标；需用户意图明确。
    """
    try:
        return as_tool_text(await run_job_to_terminal(_api(), "participate_triple"))
    except Exception as exc:
        return _err(exc)


# ----- Other writes -----


@mcp.tool()
@with_serial_lock
async def auto_start() -> str:
    """启动定时点击调度（对应定时点击坞「启动调度」）。

    先 auto_status_get 再启动。调度与 Job 互斥策略与网页一致（撞车即停等），不要并行点其它 Job。
    """
    try:
        return as_tool_text(await _api().post_json("/api/auto/start"))
    except Exception as exc:
        return _err(exc)


@mcp.tool()
@with_serial_lock
async def auto_stop() -> str:
    """停止定时点击调度（对应定时点击坞「停止调度」）。"""
    try:
        return as_tool_text(await _api().post_json("/api/auto/stop"))
    except Exception as exc:
        return _err(exc)


@mcp.tool()
@with_serial_lock
async def participate_text_save(
    text: str,
    mode: str | None = None,
) -> str:
    """保存参与文案或兜底文案（对应「保存文案」）。

    text 为要保存的内容。mode=custom 写参与文案；mode=random_comment 写兜底文案；
    mode 省略时自动读取当前设置模式。需已登录。
    """
    try:
        client = _api()
        use_mode = mode
        if not use_mode:
            settings = await client.get_json("/api/settings")
            use_mode = str((settings or {}).get("participate_text_mode") or "custom")
        value = str(text)
        body = (
            {"participate_fallback_text": value}
            if use_mode == "random_comment"
            else {"participate_text": value}
        )
        return as_tool_text(await client.put_json("/api/settings/participate-text", json_body=body))
    except Exception as exc:
        return _err(exc)


@mcp.tool()
@with_serial_lock
async def participate_text_reset() -> str:
    """恢复默认参与文案（对应「恢复默认」）。

    按当前模式写入服务端默认文案。需已登录。
    """
    try:
        client = _api()
        settings = await client.get_json("/api/settings")
        mode = str((settings or {}).get("participate_text_mode") or "custom")
        if mode == "random_comment":
            body = {
                "participate_fallback_text": str(
                    (settings or {}).get("default_participate_fallback_text")
                    or (settings or {}).get("default_participate_text")
                    or "好运连连！"
                )
            }
        else:
            body = {
                "participate_text": str(
                    (settings or {}).get("default_participate_text") or "好运连连！"
                )
            }
        return as_tool_text(await client.put_json("/api/settings/participate-text", json_body=body))
    except Exception as exc:
        return _err(exc)


@mcp.tool()
@with_serial_lock
async def participate_text_mode_set(mode: str) -> str:
    """切换参与文案模式（对应网页模式切换）。

    mode 只能是 custom（自定义文案）或 random_comment（随机借用评论）。需已登录。
    """
    try:
        mode = str(mode).strip()
        if mode not in {"custom", "random_comment"}:
            return "VALIDATION_ERROR: mode 必须是 custom 或 random_comment"
        return as_tool_text(
            await _api().put_json(
                "/api/settings/participate-text",
                json_body={"participate_text_mode": mode},
            )
        )
    except Exception as exc:
        return _err(exc)


@mcp.tool()
@with_serial_lock
async def llm_settings_save(
    api_key: str = "",
    base_url: str = "",
    model_name: str = "",
) -> str:
    """保存 LLM 配置（对应网页「保存配置」）。

    请求可含 Key，但响应仍脱敏。api_key 留空表示不修改已有 Key（与网页一致）。需已登录。
    不要在对话中回显用户提供的明文 Key。
    """
    try:
        return as_tool_text(
            await _api().post_json(
                "/api/settings/llm",
                json_body={
                    "api_key": api_key,
                    "base_url": base_url,
                    "model_name": model_name,
                },
            )
        )
    except Exception as exc:
        return _err(exc)


@mcp.tool()
@with_serial_lock
async def llm_settings_test(
    api_key: str = "",
    base_url: str = "",
    model_name: str = "",
) -> str:
    """测试 LLM 连接（对应网页「测试连接」）。

    可与保存使用相同表单字段；留空 Key 时使用已保存配置。需已登录。不要回显明文 Key。
    """
    try:
        return as_tool_text(
            await _api().post_json(
                "/api/settings/llm/test",
                json_body={
                    "api_key": api_key,
                    "base_url": base_url,
                    "model_name": model_name,
                },
            )
        )
    except Exception as exc:
        return _err(exc)


@mcp.tool()
@with_serial_lock
async def updates_check() -> str:
    """检查更新（对应网页「检查更新」）。

    查询 GitHub Releases；返回是否有新版本等结构化结果。
    """
    try:
        return as_tool_text(await _api().post_json("/api/updates/check"))
    except Exception as exc:
        return _err(exc)


@mcp.tool()
@with_serial_lock
async def diagnostics_export(job_id: int | None = None) -> str:
    """导出诊断包（对应网页「导出诊断包」）。

    返回 filename 与 text。text 可能含敏感信息，不要在对话中完整粘贴或回显密钥。
    """
    try:
        return as_tool_text(
            await _api().get_json(
                "/api/diagnostics/bundle",
                params={"job_id": job_id},
            )
        )
    except Exception as exc:
        return _err(exc)


@mcp.tool()
@with_serial_lock
async def watch_user_add(mid: int) -> str:
    """添加监控用户（对应监控名单「添加用户」）。

    mid 为 B 站用户 MID（数字）。需已登录。添加前可用 watch_users_list 避免重复。
    """
    try:
        return as_tool_text(
            await _api().post_json("/api/watch-users", json_body={"mid": int(mid)})
        )
    except Exception as exc:
        return _err(exc)


@mcp.tool()
@with_serial_lock
async def watch_user_remove(mid: int) -> str:
    """删除监控用户（对应名单中的移除）。

    mid 为要移除的用户 MID。需已登录。
    """
    try:
        return as_tool_text(await _api().delete_json(f"/api/watch-users/{int(mid)}"))
    except Exception as exc:
        return _err(exc)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
