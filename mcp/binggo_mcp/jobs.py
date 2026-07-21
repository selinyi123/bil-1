"""Job helpers: start actions and wait until terminal (G2)."""

from __future__ import annotations

import asyncio
from typing import Any

from binggo_mcp.client import BinggoApiError, BinggoClient, is_terminal_job_state

POLL_INTERVAL_SEC = 1.0
JOB_WAIT_TIMEOUT_SEC = 3600.0
QR_READY_TIMEOUT_SEC = 90.0


async def get_current_job(client: BinggoClient) -> dict[str, Any]:
    data = await client.get_json("/api/jobs/current")
    return data if isinstance(data, dict) else {}


async def wait_until_idle_or_terminal(
    client: BinggoClient,
    *,
    timeout_sec: float = JOB_WAIT_TIMEOUT_SEC,
) -> dict[str, Any]:
    """If a job is already running (e.g. from UI), wait until it finishes."""
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout_sec
    while True:
        job = await get_current_job(client)
        state = str(job.get("state") or "idle")
        if state != "running":
            return job
        if loop.time() >= deadline:
            raise BinggoApiError(
                f"等待已有任务结束超时（当前 action={job.get('action') or '—'}）。"
            )
        await asyncio.sleep(POLL_INTERVAL_SEC)


async def start_job(
    client: BinggoClient,
    action: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {"action": action}
    if params:
        body["params"] = params
    data = await client.post_json("/api/jobs", json_body=body)
    return data if isinstance(data, dict) else {"ok": True, "job": data}


async def wait_job_terminal(
    client: BinggoClient,
    *,
    expect_action: str | None = None,
    timeout_sec: float = JOB_WAIT_TIMEOUT_SEC,
) -> dict[str, Any]:
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout_sec
    last: dict[str, Any] = {}
    while True:
        last = await get_current_job(client)
        state = str(last.get("state") or "idle")
        action = str(last.get("action") or "")
        if is_terminal_job_state(state):
            if expect_action and action and action != expect_action:
                # Finished some other job; keep waiting for ours if still needed.
                pass
            else:
                return last
        if state == "idle" and not action:
            return last
        if loop.time() >= deadline:
            raise BinggoApiError(
                f"等待任务结束超时（action={expect_action or action or '—'}, state={state}）。"
            )
        await asyncio.sleep(POLL_INTERVAL_SEC)


async def run_job_to_terminal(
    client: BinggoClient,
    action: str,
    params: dict[str, Any] | None = None,
    *,
    timeout_sec: float = JOB_WAIT_TIMEOUT_SEC,
) -> dict[str, Any]:
    """Wait for any prior job, start action, wait until this job reaches a terminal state."""
    await wait_until_idle_or_terminal(client, timeout_sec=timeout_sec)
    started = await start_job(client, action, params)
    job = started.get("job") if isinstance(started.get("job"), dict) else {}
    # If server returned a snapshot already terminal (unlikely), use it.
    if is_terminal_job_state(str(job.get("state") or "")):
        return {"ok": True, "job": job, "started": started}
    final = await wait_job_terminal(client, expect_action=action, timeout_sec=timeout_sec)
    return {"ok": True, "job": final, "started": started}


def qrcode_ready(job: dict[str, Any]) -> bool:
    result = job.get("result") if isinstance(job.get("result"), dict) else {}
    if result.get("qrcode_refreshed_at"):
        return True
    phase = str(result.get("login_phase") or "")
    return phase in {"waiting", "scanned", "confirming"}


async def start_login_until_qrcode(
    client: BinggoClient,
    *,
    timeout_sec: float = QR_READY_TIMEOUT_SEC,
) -> tuple[dict[str, Any], bytes]:
    """
    Login exception to G2: return as soon as QR image is available so the user can scan.
    The login job keeps running on the server; observe with job_get.
    """
    await wait_until_idle_or_terminal(client)
    await start_job(client, "login")
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout_sec
    last: dict[str, Any] = {}
    while True:
        last = await get_current_job(client)
        state = str(last.get("state") or "")
        if is_terminal_job_state(state):
            raise BinggoApiError(
                f"登录在二维码就绪前已结束：state={state}, message={last.get('message') or ''}"
            )
        if qrcode_ready(last) or state == "running":
            try:
                png = await client.get_bytes("/api/login/qrcode")
                if png:
                    return last, png
            except BinggoApiError:
                pass
        if loop.time() >= deadline:
            raise BinggoApiError("等待登录二维码超时。")
        await asyncio.sleep(POLL_INTERVAL_SEC)


async def cancel_login_only(client: BinggoClient) -> dict[str, Any]:
    job = await get_current_job(client)
    if str(job.get("state") or "") != "running" or str(job.get("action") or "") != "login":
        raise BinggoApiError(
            "当前没有进行中的扫码登录（关闭扫码仅用于取消 login，不能取消其它任务）。"
        )
    data = await client.post_json("/api/jobs/cancel")
    return data if isinstance(data, dict) else {"ok": True, "job": data}
