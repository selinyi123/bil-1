from __future__ import annotations

import contextvars
import io
import random
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import redirect_stderr, redirect_stdout
from typing import Any, Callable

from src.app_logging import get_logger
from src.bilibili_client import BilibiliClient
from src.bilibili_login import login_with_qrcode
from src.fetch_activity_info import mark_enriched_joined
from src.log_span import PhaseSpanTracker, log_span
from src.lottery_actions import ActionResult
from src.lottery_classifier import PARTICIPATABLE_TYPES
from src.participate_preflight import ensure_activity_participatable
from src.participation import participate_activity
from src.participation_log import participation_succeeded
from src.pipeline.refresh_all_pipeline import PipelineResult, run_new_links_pipeline, run_refresh_all_pipeline
from src.sources import (
    ds1_xiaozhuli,
    ds2_fanqiao,
    ds3_gongjuren,
    ds4_junming,
    ds5_hudong,
    ds6_nuomi,
    ds7_dajinli,
    ds8_manual,
    ds9_tags,
    ds10_api,
)
from src.sources.common import CheckResult, commit_source_checkpoint, is_valid_dynamic_id
from src.state_store import set_last_pipeline_persisted, set_watch_last_synced_at
from src.status_refresh import refresh_local_activity_statuses
from web.activity_service import (
    PARTICIPATE_TRIPLE_LIMIT,
    build_triple_progress_plan,
    build_triple_target_preview,
    invalidate_activity_cache,
    lookup_lottery_type,
    participate_step_budget,
    pick_triple_participate_targets,
    resolve_participate_lottery_type,
)
from src.watch_sync import save_watch_result, sync_watch_forwards
from web.user_messages import format_participation_log, sanitize_log

logger = get_logger("job")

PARTICIPATE_TRIPLE_WORKERS = PARTICIPATE_TRIPLE_LIMIT
REFRESH_ALL_PIPELINE_SUBSTEPS = 3
REFRESH_WATCH_PIPELINE_SUBSTEPS = 3
REFRESH_WATCH_TOTAL = 1 + REFRESH_WATCH_PIPELINE_SUBSTEPS


def _deserialize_payload_actions(payload: dict[str, Any]) -> list[ActionResult]:
    actions: list[ActionResult] = []
    for item in payload.get("actions") or []:
        if not isinstance(item, dict):
            continue
        action_name = str(item.get("action") or "").strip()
        if not action_name:
            continue
        actions.append(
            ActionResult(
                action=action_name,  # type: ignore[arg-type]
                ok=bool(item.get("ok")),
                detail=str(item.get("detail") or ""),
            )
        )
    return actions


def _payload_joined_success(payload: dict[str, Any]) -> bool:
    if str(payload.get("status") or "") != "joined":
        return False
    lottery_type = str(payload.get("lottery_type") or "")
    actions = _deserialize_payload_actions(payload)
    if not actions:
        return False
    if lottery_type in ("互动抽奖", "转发抽奖", "预约抽奖"):
        return participation_succeeded(actions, lottery_type=lottery_type)
    return all(item.ok for item in actions)


def _require_participate_success(payload: dict[str, Any]) -> None:
    status = str(payload.get("status") or "")
    if status == "dry_run":
        # 预演模式：返回"将执行"的清单即视为成功，不要求真实 joined
        return
    if status == "skipped":
        raise RuntimeError(str(payload.get("message") or "该活动不可参与"))
    if status != "joined" or not _payload_joined_success(payload):
        raise RuntimeError(str(payload.get("message") or "参与失败"))


def _normalize_participate_payload(payload: dict[str, Any]) -> dict[str, Any]:
    _require_participate_success(payload)
    return dict(payload)


def _participate_dynamic_payload(
    dynamic_id: str,
    on_step: Callable[[int, int, str, str], None],
    *,
    lottery_type_hint: str | None = None,
    client: BilibiliClient | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    resolved_type = resolve_participate_lottery_type(dynamic_id, hint=lottery_type_hint)
    if client is not None:
        payload = _execute_participate(
            dynamic_id,
            on_step,
            lottery_type=resolved_type,
            client=client,
            dry_run=dry_run,
        )
    else:
        payload, _detail = _capture_output(
            _execute_participate,
            dynamic_id,
            on_step,
            lottery_type=resolved_type,
            dry_run=dry_run,
        )
    return _normalize_participate_payload(payload)


def _list_filter_params(params: dict[str, Any]) -> dict[str, str | None]:
    return {
        "status": str(params.get("status") or "").strip() or None,
        "lottery_type": str(params.get("lottery_type") or params.get("type") or "").strip() or None,
        "draw": str(params.get("draw") or "").strip() or None,
        "draw_window": str(params.get("draw_window") or "").strip() or None,
        "q": str(params.get("q") or "").strip() or None,
        "sort": str(params.get("sort") or "").strip() or None,
        "order": str(params.get("order") or "").strip() or None,
    }


def _execute_participate(
    dynamic_id: str,
    on_step: Callable[[int, int, str, str], None],
    *,
    lottery_type: str | None = None,
    client: BilibiliClient | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    dynamic_id = str(dynamic_id or "").strip()
    if not is_valid_dynamic_id(dynamic_id):
        raise ValueError(f"活动 ID 无效: {dynamic_id}")
    resolved_type = str(lottery_type or "").strip()
    if resolved_type not in PARTICIPATABLE_TYPES:
        resolved_type = resolve_participate_lottery_type(dynamic_id)

    def _run(active_client: BilibiliClient) -> dict[str, Any]:
        result = participate_activity(
            active_client,
            dynamic_id=dynamic_id,
            lottery_type=resolved_type,
            # 预演模式贯穿到底层：dry_run=true 时绝不产生真实副作用（点赞/关注/转发/评论）
            dry_run=dry_run,
            persist=not dry_run,
            on_step=on_step,
        )
        payload = result.to_dict()
        payload["lottery_type"] = resolved_type
        return payload

    if client is not None:
        return _run(client)
    with BilibiliClient() as owned_client:
        return _run(owned_client)


def _append_log_detail(log_lines: list[str], detail: str) -> None:
    cleaned = sanitize_log(detail.strip())
    if cleaned:
        log_lines.append(cleaned)


DS_HANDLERS: list[tuple[str, Callable[..., Any], Callable[[Any], Any]]] = [
    ("DS-1", ds1_xiaozhuli.check_update, ds1_xiaozhuli.save_result),
    ("DS-2", ds2_fanqiao.check_update, ds2_fanqiao.save_result),
    ("DS-3", ds3_gongjuren.check_update, ds3_gongjuren.save_result),
    ("DS-4", ds4_junming.check_update, ds4_junming.save_result),
    ("DS-5", ds5_hudong.check_update, ds5_hudong.save_result),
    ("DS-6", ds6_nuomi.check_update, ds6_nuomi.save_result),
    ("DS-7", ds7_dajinli.check_update, ds7_dajinli.save_result),
    ("DS-8", ds8_manual.check_update, ds8_manual.save_result),
    ("DS-9", ds9_tags.check_update, ds9_tags.save_result),
    ("DS-10", ds10_api.check_update, ds10_api.save_result),
]
DS_HANDLER_BY_ID: dict[str, tuple[Callable[..., Any], Callable[[Any], Any]]] = {
    source_id: (check_update, save_result)
    for source_id, check_update, save_result in DS_HANDLERS
}

REFRESH_ALL_TOTAL = len(DS_HANDLERS) + REFRESH_ALL_PIPELINE_SUBSTEPS
REFRESH_SOURCE_TOTAL = 1 + REFRESH_ALL_PIPELINE_SUBSTEPS
ProgressCallback = Callable[..., None]


_SUBPROGRESS_SUFFIX_RE = re.compile(r"(?:\s*\(\s*\d+\s*/\s*\d+\s*\))+\s*$")


def _format_subprogress_message(message: str, done: int, total: int) -> str:
    base = _SUBPROGRESS_SUFFIX_RE.sub("", str(message or "").strip()).strip()
    if total <= 0:
        return base
    return f"{base} ({done}/{total})"


def _pipeline_substep_index(message: str) -> int:
    text = str(message or "")
    if "入库" in text or "落库" in text or "写入活动库" in text:
        return 3
    if "详情进度" in text or "活动详情" in text:
        return 2
    if "分类" in text or "新链接" in text:
        return 1
    return 1


_PIPELINE_PHASE_BY_SUBSTEP = {
    1: ("pipeline_classify", "pipeline_classify"),
    2: ("pipeline_detail", "pipeline_detail"),
    3: ("pipeline_persist", "pipeline_persist"),
}


def _make_refresh_all_pipeline_progress(
    progress: ProgressCallback,
    *,
    ds_count: int,
    span_tracker: PhaseSpanTracker | None = None,
) -> Callable[[int, int, str], None]:
    def on_pipeline_progress(done: int, total: int, message: str) -> None:
        substep = _pipeline_substep_index(message)
        if span_tracker is not None:
            phase_name = _PIPELINE_PHASE_BY_SUBSTEP.get(substep)
            if phase_name:
                phase, span_name = phase_name
                span_tracker.set_phase(phase, name=span_name)
        progress(
            step=ds_count + substep,
            total=REFRESH_ALL_TOTAL,
            message=_format_subprogress_message(message, done, total),
        )

    return on_pipeline_progress


def _make_refresh_watch_pipeline_progress(
    progress: ProgressCallback,
    *,
    span_tracker: PhaseSpanTracker | None = None,
) -> Callable[[int, int, str], None]:
    def on_pipeline_progress(done: int, total: int, message: str) -> None:
        substep = _pipeline_substep_index(message)
        if span_tracker is not None:
            phase_name = _PIPELINE_PHASE_BY_SUBSTEP.get(substep)
            if phase_name:
                phase, span_name = phase_name
                span_tracker.set_phase(phase, name=span_name)
        progress(
            step=1 + substep,
            total=REFRESH_WATCH_TOTAL,
            message=_format_subprogress_message(message, done, total),
        )

    return on_pipeline_progress


def _noop_progress(**_kwargs: Any) -> None:
    return None


def _parse_bool(value: Any, default: bool = False) -> bool:
    """宽松布尔解析：支持 bool / "true"/"false"/"1"/"0"/"yes"/"no" 字符串。"""
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _capture_output(func: Callable[..., Any], *args: Any, **kwargs: Any) -> tuple[Any, str]:
    buffer = io.StringIO()
    with redirect_stdout(buffer), redirect_stderr(buffer):
        result = func(*args, **kwargs)
    return result, buffer.getvalue()


def _pipeline_log_lines(result: PipelineResult) -> list[str]:
    if result.pipeline_skipped:
        return [f"【流水线】{result.message}"]
    skip_detail = ""
    if result.skip_reasons:
        parts = [f"{reason} {count}" for reason, count in result.skip_reasons.items()]
        skip_detail = f"，跳过 {result.skipped_count} 条（{' / '.join(parts)}）"
    return [
        f"【新链接流水线】候选 {result.new_link_count} 条，"
        f"分类通过 {result.classified_count} 条，"
        f"详情 {result.enriched_count} 条，"
        f"入库 {result.persisted_count} 条{skip_detail}"
    ]


def _run_ds_check(
    index: int,
    source_id: str,
    check_update: Callable[..., Any],
    save_result: Callable[[Any], Any],
) -> tuple[int, dict[str, Any], str, CheckResult]:
    with log_span(
        f"ds_check:{source_id}",
        logger=logger,
        component="ds",
        source_id=source_id,
        phase="ds_check",
    ):
        result, detail = _capture_output(check_update, force=False)
        out_path = save_result(result)
    status_text = "发现新专栏，已爬取" if result.updated else "同一专栏，已跳过"
    log_line = f"【{source_id}】{status_text}，共 {len(result.activity_links)} 条链接"
    payload = {
        "source_id": source_id,
        "updated": result.updated,
        "link_count": len(result.activity_links),
        "saved": bool(out_path),
        "log_line": log_line,
        "detail": detail.strip(),
        "status_text": status_text,
    }
    return index, payload, log_line, result


def _raise_if_cancelled(cancel_event: threading.Event | None) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise ValueError("任务已取消")


class TripleParticipateAborted(RuntimeError):
    """三连内部 fail-fast：某活动失败后中止其他活动（区别于用户取消）。"""


class TripleParticipateFailed(RuntimeError):
    """三连参与失败：至少一个活动内部失败，任务终态应为 error 而非 cancelled。

    携带失败前已完成的活动摘要（partial_failure 语义：外部副作用不可回滚，
    必须让调用方/UI 知道哪些活动实际完成了哪些动作）。
    """

    def __init__(
        self,
        message: str,
        *,
        completed: list[dict[str, Any]] | None = None,
        failed_dynamic_id: str = "",
    ) -> None:
        super().__init__(message)
        self.completed = completed or []
        self.failed_dynamic_id = failed_dynamic_id


def run_action(
    action: str,
    params: dict[str, Any] | None = None,
    *,
    on_progress: ProgressCallback | None = None,
    cancel_event: threading.Event | None = None,
) -> dict[str, Any]:
    params = params or {}
    progress = on_progress or _noop_progress
    log_lines: list[str] = []
    _raise_if_cancelled(cancel_event)

    if action == "login":
        qrcode_refresh_count = 0

        def on_qrcode_ready() -> None:
            nonlocal qrcode_refresh_count
            qrcode_refresh_count += 1
            refreshed_at = int(time.time())
            if qrcode_refresh_count == 1:
                progress(
                    step=1,
                    total=1,
                    message="请使用哔哩哔哩 App 扫码登录",
                    log_append="已生成登录二维码",
                    login_phase="waiting",
                    qrcode_refreshed_at=refreshed_at,
                )
            else:
                progress(
                    step=1,
                    total=1,
                    message="二维码已刷新，请重新扫码",
                    log_append="二维码已自动刷新",
                    login_phase="waiting",
                    qrcode_refreshed_at=refreshed_at,
                )

        def on_login_status(phase: str, message: str) -> None:
            log_append = {
                "scanned": "已在手机扫码，等待确认",
                "confirming": "用户已确认，正在写入登录信息",
                "refreshing": "二维码已过期，请重新扫码",
            }.get(phase)
            progress(
                step=1,
                total=1,
                message=message,
                log_append=log_append,
                login_phase=phase,
            )

        progress(step=1, total=1, message="正在生成登录二维码…", login_phase="waiting")
        result, log = _capture_output(
            login_with_qrcode,
            open_image=False,
            auto_refresh_on_expire=False,
            cancel_event=cancel_event,
            on_qrcode_ready=on_qrcode_ready,
            on_status_change=on_login_status,
        )
        # 登记到账号池（config/accounts/{uid}.txt + 活跃标记）；登录失败时 result 为空
        from src.account_pool import register_login_cookie

        registered_uid = register_login_cookie(result) if result else None
        progress(
            step=1,
            total=1,
            message="登录成功，账号已就绪",
            login_phase="success",
            result_patch={"registered_uid": registered_uid},
        )
        return {
            "ok": True,
            "message": "登录成功，账号已就绪",
            "log": sanitize_log(log) or "登录成功",
            "result": {"login_phase": "success", "registered_uid": registered_uid},
        }

    if action == "refresh_all":
        ds_results: list[dict[str, Any]] = []
        sources_updated = 0
        sources_failed = 0
        progress(
            step=0,
            total=REFRESH_ALL_TOTAL,
            message=f"正在并行检查 {len(DS_HANDLERS)} 个数据源…",
        )
        _raise_if_cancelled(cancel_event)

        ds_payloads: list[tuple[int, dict[str, Any], str, CheckResult]] = []
        with ThreadPoolExecutor(max_workers=len(DS_HANDLERS)) as executor:
            # 每个 future 各自 copy_context：同一 Context 不能被多线程并发 enter
            futures = {
                executor.submit(
                    contextvars.copy_context().run,
                    _run_ds_check,
                    index,
                    source_id,
                    check_update,
                    save_result,
                ): source_id
                for index, (source_id, check_update, save_result) in enumerate(DS_HANDLERS, start=1)
            }
            for future in as_completed(futures):
                _raise_if_cancelled(cancel_event)
                source_id = futures[future]
                try:
                    ds_payloads.append(future.result())
                except Exception as exc:
                    logger.warning("%s 检查失败，跳过该源: %s", source_id, exc)
                    sources_failed += 1
                    ds_results.append(
                        {
                            "source_id": source_id,
                            "updated": False,
                            "link_count": 0,
                            "saved": False,
                            "error": str(exc),
                        }
                    )
                    log_lines.append(f"【{source_id}】检查失败已跳过：{exc}")

        ds_payloads.sort(key=lambda item: item[0])
        ds_check_results: list[CheckResult] = []
        for index, payload, log_line, check_result in ds_payloads:
            _raise_if_cancelled(cancel_event)
            ds_check_results.append(check_result)
            if payload.get("updated"):
                sources_updated += 1
            ds_results.append(
                {
                    "source_id": payload["source_id"],
                    "updated": payload["updated"],
                    "link_count": payload["link_count"],
                    "saved": payload["saved"],
                }
            )
            log_lines.append(log_line)
            progress(
                step=index,
                total=REFRESH_ALL_TOTAL,
                message=f"{payload['source_id']}：{payload['status_text']}",
                log_append=log_line,
            )

        if sources_updated == 0:
            failed_text = (
                f"，{sources_failed} 个数据源检查失败"
                if sources_failed
                else ""
            )
            if sources_failed == len(DS_HANDLERS):
                # 全部数据源失败：必须显式失败，绝不伪装成"无更新"
                fail_line = (
                    f"【失败】全部 {len(DS_HANDLERS)} 个数据源检查失败，"
                    "活动库未刷新（请检查网络/数据源配置）"
                )
                log_lines.append(fail_line)
                progress(
                    step=REFRESH_ALL_TOTAL,
                    total=REFRESH_ALL_TOTAL,
                    message=fail_line,
                    log_append=fail_line,
                )
                logger.error("一键更新失败：全部数据源检查失败")
                set_last_pipeline_persisted(action="refresh_all", persisted_count=0)
                return {
                    "ok": False,
                    "message": fail_line,
                    "result": {
                        "sources": ds_results,
                        "sources_updated": 0,
                        "sources_failed": sources_failed,
                        "pipeline_skipped": True,
                        "new_link_count": 0,
                        "persisted_count": 0,
                    },
                    "log": sanitize_log("\n".join(log_lines).strip()),
                }
            # 无更新（可能有部分失败）：降级提示，仍为完成态
            skip_line = (
                f"【跳过流水线】{len(DS_HANDLERS)} 个数据源均无新专栏{failed_text}，跳过后续步骤"
            )
            log_lines.append(skip_line)
            progress(
                step=REFRESH_ALL_TOTAL,
                total=REFRESH_ALL_TOTAL,
                message="均无新专栏，已跳过整个流水线" + failed_text,
                log_append=skip_line,
            )
            logger.info(
                "一键更新：%s 个数据源均无新专栏%s，跳过流水线",
                len(DS_HANDLERS),
                failed_text,
            )
            set_last_pipeline_persisted(action="refresh_all", persisted_count=0)
            return {
                "ok": True,
                "message": (
                    f"检查完成：{len(DS_HANDLERS)} 个数据源均无新专栏{failed_text}，"
                    "已跳过整个流水线"
                ),
                "result": {
                    "sources": ds_results,
                    "sources_updated": 0,
                    "sources_failed": sources_failed,
                    "pipeline_skipped": True,
                    "new_link_count": 0,
                    "persisted_count": 0,
                },
                "log": sanitize_log("\n".join(log_lines).strip()),
            }

        _raise_if_cancelled(cancel_event)
        pipeline_step = len(DS_HANDLERS) + 1
        progress(step=pipeline_step, total=REFRESH_ALL_TOTAL, message="正在分类新链接…")

        pipeline_spans = PhaseSpanTracker(logger=logger, component="pipeline")
        pipeline_error: str | None = None
        try:
            pipeline_result = run_refresh_all_pipeline(
                ds_check_results,
                on_progress=_make_refresh_all_pipeline_progress(
                    progress,
                    ds_count=len(DS_HANDLERS),
                    span_tracker=pipeline_spans,
                ),
            )
        except Exception as exc:
            pipeline_error = type(exc).__name__
            raise
        finally:
            pipeline_spans.close(error_kind=pipeline_error)
        _raise_if_cancelled(cancel_event)
        for check_result in ds_check_results:
            commit_source_checkpoint(check_result)
        invalidate_activity_cache()
        for line in _pipeline_log_lines(pipeline_result):
            log_lines.append(line)
        progress(
            step=REFRESH_ALL_TOTAL,
            total=REFRESH_ALL_TOTAL,
            message=pipeline_result.message or "流水线完成",
            log_append=log_lines[-1] if log_lines else "",
        )

        summary_parts = [
            f"检查 {len(DS_HANDLERS)} 个数据源，{sources_updated} 个有新专栏",
            f"新链接 {pipeline_result.new_link_count} 条",
            f"新入库 {pipeline_result.persisted_count} 条",
        ]
        if pipeline_result.skip_reasons:
            summary_parts.append(f"跳过 {pipeline_result.skipped_count} 条")

        logger.info(
            "一键更新完成：新链接 %s，入库 %s",
            pipeline_result.new_link_count,
            pipeline_result.persisted_count,
        )
        set_last_pipeline_persisted(
            action="refresh_all",
            persisted_count=pipeline_result.persisted_count,
        )

        return {
            "ok": True,
            "message": "一键更新完成：" + "，".join(summary_parts),
            "result": {
                "sources": ds_results,
                "sources_updated": sources_updated,
                "pipeline": pipeline_result.to_dict(),
            },
            "log": sanitize_log("\n".join(log_lines).strip()),
        }

    if action == "refresh_source":
        source_id = str(params.get("source_id") or "").strip()
        handler = DS_HANDLER_BY_ID.get(source_id)
        if not handler:
            raise ValueError(f"未知数据源：{source_id}")
        check_update, save_result = handler

        progress(
            step=0,
            total=REFRESH_SOURCE_TOTAL,
            message=f"正在检查 {source_id}…",
        )
        _raise_if_cancelled(cancel_event)
        _, payload, log_line, check_result = _run_ds_check(1, source_id, check_update, save_result)
        _raise_if_cancelled(cancel_event)
        log_lines.append(log_line)
        progress(
            step=1,
            total=REFRESH_SOURCE_TOTAL,
            message=f"{source_id}：{payload['status_text']}",
            log_append=log_line,
        )

        if not check_result.updated:
            skip_line = f"【跳过流水线】{source_id} 为同一专栏，跳过后续步骤"
            log_lines.append(skip_line)
            progress(
                step=REFRESH_SOURCE_TOTAL,
                total=REFRESH_SOURCE_TOTAL,
                message="无新专栏，已跳过流水线",
                log_append=skip_line,
            )
            logger.info("%s 无新专栏，跳过流水线", source_id)
            set_last_pipeline_persisted(action="refresh_source", persisted_count=0)
            return {
                "ok": True,
                "message": f"{source_id} 检查完成：无新专栏，已跳过流水线",
                "result": {
                    "source_id": source_id,
                    "source": {
                        "source_id": payload["source_id"],
                        "updated": payload["updated"],
                        "link_count": payload["link_count"],
                        "saved": payload["saved"],
                    },
                    "pipeline_skipped": True,
                    "new_link_count": 0,
                    "persisted_count": 0,
                },
                "log": sanitize_log("\n".join(log_lines).strip()),
            }

        _raise_if_cancelled(cancel_event)
        progress(step=2, total=REFRESH_SOURCE_TOTAL, message="正在分类新链接…")
        pipeline_spans = PhaseSpanTracker(logger=logger, component="pipeline")
        pipeline_error: str | None = None
        try:
            pipeline_result = run_refresh_all_pipeline(
                [check_result],
                on_progress=_make_refresh_all_pipeline_progress(
                    progress,
                    ds_count=1,
                    span_tracker=pipeline_spans,
                ),
            )
        except Exception as exc:
            pipeline_error = type(exc).__name__
            raise
        finally:
            pipeline_spans.close(error_kind=pipeline_error)
        _raise_if_cancelled(cancel_event)
        commit_source_checkpoint(check_result)
        invalidate_activity_cache()
        for line in _pipeline_log_lines(pipeline_result):
            log_lines.append(line)
        progress(
            step=REFRESH_SOURCE_TOTAL,
            total=REFRESH_SOURCE_TOTAL,
            message=pipeline_result.message or "流水线完成",
            log_append=log_lines[-1] if log_lines else "",
        )

        summary_parts = [
            f"{source_id} 有新专栏",
            f"新链接 {pipeline_result.new_link_count} 条",
            f"新入库 {pipeline_result.persisted_count} 条",
        ]
        if pipeline_result.skip_reasons:
            summary_parts.append(f"跳过 {pipeline_result.skipped_count} 条")

        logger.info(
            "%s 更新完成：新链接 %s，入库 %s",
            source_id,
            pipeline_result.new_link_count,
            pipeline_result.persisted_count,
        )
        set_last_pipeline_persisted(
            action="refresh_source",
            persisted_count=pipeline_result.persisted_count,
        )

        return {
            "ok": True,
            "message": f"{source_id} 更新完成：" + "，".join(summary_parts),
            "result": {
                "source_id": source_id,
                "source": {
                    "source_id": payload["source_id"],
                    "updated": payload["updated"],
                    "link_count": payload["link_count"],
                    "saved": payload["saved"],
                },
                "pipeline": pipeline_result.to_dict(),
            },
            "log": sanitize_log("\n".join(log_lines).strip()),
        }

    if action == "refresh_watch":
        log_lines: list[str] = []
        progress(step=0, total=REFRESH_WATCH_TOTAL, message="准备扫描监控用户动态…")
        _raise_if_cancelled(cancel_event)

        def on_watch_progress(done: int, total: int, message: str) -> None:
            _raise_if_cancelled(cancel_event)
            progress(step=1, total=REFRESH_WATCH_TOTAL, message=message)

        with log_span("watch_scan", logger=logger, component="pipeline", phase="watch_scan"):
            watch_result = sync_watch_forwards(on_progress=on_watch_progress)
        _raise_if_cancelled(cancel_event)
        watch_line = (
            f"【监控扫描】窗口内 {watch_result.link_count} 条活动链接，"
            f"成功扫描 {watch_result.users_ok}/{watch_result.users_total} 人"
        )
        log_lines.append(watch_line)
        progress(
            step=1,
            total=REFRESH_WATCH_TOTAL,
            message=f"扫描完成：窗口 {watch_result.link_count} 条链接",
            log_append=watch_line,
        )

        pipeline_step = 2
        progress(step=pipeline_step, total=REFRESH_WATCH_TOTAL, message="正在分类新链接…")
        _raise_if_cancelled(cancel_event)

        pipeline_spans = PhaseSpanTracker(logger=logger, component="pipeline")
        pipeline_error: str | None = None
        try:
            pipeline_result = run_new_links_pipeline(
                watch_result.activity_links,
                on_progress=_make_refresh_watch_pipeline_progress(
                    progress,
                    span_tracker=pipeline_spans,
                ),
            )
        except Exception as exc:
            pipeline_error = type(exc).__name__
            raise
        finally:
            pipeline_spans.close(error_kind=pipeline_error)
        _raise_if_cancelled(cancel_event)
        invalidate_activity_cache()
        for line in _pipeline_log_lines(pipeline_result):
            log_lines.append(line)
        progress(
            step=REFRESH_WATCH_TOTAL,
            total=REFRESH_WATCH_TOTAL,
            message=pipeline_result.message or "流水线完成",
            log_append=log_lines[-1] if log_lines else "",
        )

        set_watch_last_synced_at(watch_result.synced_at)
        save_watch_result(watch_result)
        set_last_pipeline_persisted(
            action="refresh_watch",
            persisted_count=pipeline_result.persisted_count,
            synced_at=watch_result.synced_at,
        )

        summary_parts = [
            f"扫描 {watch_result.users_total} 人，提取 {watch_result.link_count} 条链接",
            f"新链接 {pipeline_result.new_link_count} 条",
            f"新入库 {pipeline_result.persisted_count} 条",
        ]
        logger.info(
            "监控用户更新完成：窗口 %s 条，入库 %s",
            watch_result.link_count,
            pipeline_result.persisted_count,
        )
        return {
            "ok": True,
            "message": "监控用户动态更新完成：" + "，".join(summary_parts),
            "result": {
                "watch": watch_result.to_dict(),
                "pipeline": pipeline_result.to_dict(),
            },
            "log": sanitize_log("\n".join(log_lines).strip()),
        }

    if action == "refresh_status":
        progress(step=0, total=1, message="正在刷新活动状态…")
        _raise_if_cancelled(cancel_event)
        with log_span(
            "status_refresh",
            logger=logger,
            component="pipeline",
            phase="status_refresh",
        ):
            result = refresh_local_activity_statuses()
        _raise_if_cancelled(cancel_event)
        invalidate_activity_cache()
        if result.get("skipped"):
            message = "没有需要刷新的进行中活动"
        else:
            message = (
                f"状态刷新完成：检查 {result.get('scanned', 0)} 条，"
                f"更新 {result.get('updated', 0)} 条，"
                f"新结束 {result.get('ended_marked', 0)} 条，"
                f"即将开奖 {result.get('soon_marked', 0)} 条"
            )
        progress(step=1, total=1, message=message, log_append=message)
        logger.info(
            "刷新任务状态完成：检查 %s，更新 %s",
            result.get("scanned", 0),
            result.get("updated", 0),
        )
        return {
            "ok": True,
            "message": message,
            "result": result,
            "log": sanitize_log(message),
        }

    if action == "participate":
        dynamic_id = str(params.get("dynamic_id") or "").strip()
        if not is_valid_dynamic_id(dynamic_id):
            raise ValueError("活动 ID 无效")
        _raise_if_cancelled(cancel_event)
        try:
            lottery_type = lookup_lottery_type(dynamic_id)
        except RuntimeError as exc:
            logger.warning("参与失败：未找到活动类型 %s — %s", dynamic_id, exc)
            raise ValueError(f"未找到活动 {dynamic_id} 的类型信息，请先一键更新") from exc
        total_steps = participate_step_budget(lottery_type, dynamic_id=dynamic_id)
        progress(step=0, total=total_steps, message="正在检查活动状态…", log_append="正在打开活动链接检查状态…")
        logger.info("开始参与活动 %s (%s)", dynamic_id, lottery_type)

        def on_step(step: int, total: int, message: str, _action_name: str) -> None:
            _raise_if_cancelled(cancel_event)
            progress(step=step, total=total, message=message, log_append=message)

        dry_run = _parse_bool(params.get("dry_run"), default=False)
        with BilibiliClient() as client:
            _raise_if_cancelled(cancel_event)
            ensure_activity_participatable(client, dynamic_id, lottery_type_hint=lottery_type)
            _raise_if_cancelled(cancel_event)
            progress(step=0, total=total_steps, message="检查通过，开始参与…", log_append="活动可参与，开始执行参与步骤")
            payload = _participate_dynamic_payload(
                dynamic_id,
                on_step,
                lottery_type_hint=lottery_type,
                client=client,
                dry_run=dry_run,
            )

        if not dry_run:
            mark_enriched_joined(dynamic_id)
        refresh_local_activity_statuses()
        logger.info("参与活动成功 %s", dynamic_id)
        action_log = format_participation_log(payload)
        invalidate_activity_cache()
        return {
            "ok": True,
            "message": str(payload.get("message") or "参与成功"),
            "result": payload,
            "log": action_log,
        }

    if action == "participate_triple":
        _raise_if_cancelled(cancel_event)

        filters = _list_filter_params(params)
        targets = pick_triple_participate_targets(**filters)
        from_auto = bool(params.get("from_auto"))
        # 乱序参与（源自 LAS）：防固定顺序被开奖机过滤，缺省开启
        from src.participate_enhance import load_participate_enhance

        if load_participate_enhance().get("shuffle_targets", True) and len(targets) > 1:
            random.shuffle(targets)
        if not targets:
            return {
                "ok": True,
                "message": "当前没有可参与的未参加活动，已跳过",
                "log": "无可参与目标，本次三连参与已跳过",
                "result": {
                    "skipped": True,
                    "from_auto": from_auto,
                    "joined": 0,
                    "failed": 0,
                    "items": [],
                    "targets": [],
                },
            }

        target_titles = [str(item.get("activity_title") or item.get("dynamic_id") or "") for item in targets]
        total_steps, progress_plan = build_triple_progress_plan(targets)
        if total_steps <= 0:
            return {
                "ok": True,
                "message": "当前没有可参与的未参加活动，已跳过",
                "log": "进度计划为空，本次三连参与已跳过",
                "result": {
                    "skipped": True,
                    "from_auto": from_auto,
                    "joined": 0,
                    "failed": 0,
                    "items": [],
                    "targets": [],
                },
            }

        logger.info("三连参与开始：%s", ", ".join(target_titles))
        triple_target_items = build_triple_target_preview(targets)["items"]
        progress(
            step=0,
            total=total_steps,
            message=f"准备并行三连参与 {len(targets)} 个活动…",
            log_append="目标活动：" + "、".join(target_titles),
            result_patch={"targets": triple_target_items},
        )

        progress_lock = threading.Lock()
        # 内部 fail-fast 事件：某活动失败后中止其他活动。
        # 与用户取消（cancel_event）语义分离——内部失败绝不 set cancel_event，
        # 避免 JobRunner 把业务失败误判成"用户取消"。
        fail_fast_event = threading.Event()
        task_states: dict[str, str] = {
            str(item.get("dynamic_id") or ""): "等待开始…" for item in targets
        }
        task_step_progress: dict[str, int] = {
            str(item.get("dynamic_id") or ""): 0 for item in targets
        }
        # 已开始执行（on_step 上报）的动作名，用于失败摘要如实反映外部副作用
        task_executed_actions: dict[str, list[str]] = {
            str(item.get("dynamic_id") or ""): [] for item in targets
        }
        target_ids = [str(item.get("dynamic_id") or "") for item in targets]

        def _overall_progress_step() -> int:
            total_done = 0
            for dynamic_id in target_ids:
                plan_entry = progress_plan.get(dynamic_id)
                if not plan_entry:
                    continue
                _, budget = plan_entry
                total_done += min(task_step_progress.get(dynamic_id, 0), budget)
            return min(total_done, total_steps)

        def _emit_triple_progress(*, log_append: str | None = None) -> None:
            progress(
                step=_overall_progress_step(),
                total=total_steps,
                message=_progress_snapshot(),
                log_append=log_append,
            )

        def _progress_snapshot() -> str:
            parts: list[str] = []
            for target in targets:
                dynamic_id = str(target.get("dynamic_id") or "")
                title = str(target.get("activity_title") or dynamic_id[-6:])
                parts.append(f"{title}: {task_states.get(dynamic_id, '等待开始…')}")
            return " | ".join(parts)

        def _report_task_progress(
            dynamic_id: str,
            step: int,
            _total: int,
            message: str,
            action_name: str = "",
        ) -> None:
            if cancel_event and cancel_event.is_set():
                raise ValueError("任务已取消")
            if fail_fast_event.is_set():
                raise TripleParticipateAborted("其他活动失败，本活动已停止")
            if dynamic_id not in progress_plan:
                return
            with progress_lock:
                task_states[dynamic_id] = message
                task_step_progress[dynamic_id] = max(task_step_progress.get(dynamic_id, 0), step)
                if action_name:
                    executed = task_executed_actions.setdefault(dynamic_id, [])
                    if action_name not in executed:
                        executed.append(action_name)
            title = next(
                (
                    str(item.get("activity_title") or dynamic_id)
                    for item in targets
                    if str(item.get("dynamic_id") or "") == dynamic_id
                ),
                dynamic_id,
            )
            _emit_triple_progress(log_append=f"{title}：{message}")

        def _mark_other_tasks_stopped(failed_id: str, *, reason: str) -> None:
            skip_markers = ("失败", "参与成功", "完成", "成功", "已停止", "已取消")
            with progress_lock:
                for other_id in target_ids:
                    if failed_id and other_id == failed_id:
                        continue
                    state = task_states.get(other_id, "")
                    if any(marker in state for marker in skip_markers):
                        continue
                    task_states[other_id] = reason

        def _participate_triple_target(target: dict[str, Any]) -> dict[str, Any]:
            if cancel_event and cancel_event.is_set():
                raise ValueError("任务已取消")
            if fail_fast_event.is_set():
                raise TripleParticipateAborted("其他活动失败，本活动已停止")

            dynamic_id = str(target.get("dynamic_id") or "")
            title = str(target.get("activity_title") or dynamic_id)
            target_lottery_type = str(target.get("lottery_type") or "").strip() or None

            with progress_lock:
                task_states[dynamic_id] = "正在检查活动状态…"
            _emit_triple_progress(log_append=f"{title}：正在检查活动状态…")

            with BilibiliClient() as client:
                ensure_activity_participatable(
                    client,
                    dynamic_id,
                    lottery_type_hint=target_lottery_type,
                )
                if cancel_event and cancel_event.is_set():
                    raise ValueError("任务已取消")
                if fail_fast_event.is_set():
                    raise TripleParticipateAborted("其他活动失败，本活动已停止")

                def on_step(step: int, total: int, message: str, action_name: str) -> None:
                    _report_task_progress(dynamic_id, step, total, message, action_name)

                payload = _participate_dynamic_payload(
                    dynamic_id,
                    on_step,
                    lottery_type_hint=target_lottery_type,
                    client=client,
                )

            mark_enriched_joined(dynamic_id)
            with progress_lock:
                task_states[dynamic_id] = str(payload.get("message") or "参与成功")
            plan_entry = progress_plan.get(dynamic_id)
            if plan_entry:
                _, budget = plan_entry
                task_step_progress[dynamic_id] = budget
            _emit_triple_progress(log_append=f"{title}：参与成功")
            return {
                "dynamic_id": dynamic_id,
                "activity_title": title,
                "lottery_type": str(payload.get("lottery_type") or target.get("lottery_type") or ""),
                "payload": payload,
            }

        results: list[dict[str, Any]] = []
        _emit_triple_progress()
        with ThreadPoolExecutor(max_workers=PARTICIPATE_TRIPLE_WORKERS) as executor:
            # 每个 future 各自 copy_context：同一 Context 不能被多线程并发 enter
            future_to_id = {
                executor.submit(
                    contextvars.copy_context().run,
                    _participate_triple_target,
                    target,
                ): str(target.get("dynamic_id") or "")
                for target in targets
            }
            try:
                for future in as_completed(future_to_id):
                    dynamic_id = future_to_id[future]
                    if cancel_event and cancel_event.is_set():
                        raise ValueError("任务已取消")
                    try:
                        results.append(future.result())
                    except TripleParticipateAborted:
                        # 被 fail-fast 中止的活动：已由主失败路径标记，忽略
                        continue
                    except Exception as exc:
                        # 内部失败：设置 fail-fast（不 set cancel_event），
                        # 取消未开始的任务并抛出业务失败异常 → JobRunner 终态 error。
                        # 已完成的活动摘要随异常携带（partial_failure 语义）。
                        fail_fast_event.set()
                        with progress_lock:
                            task_states[dynamic_id] = f"失败：{exc}"
                        _mark_other_tasks_stopped(dynamic_id, reason="已停止（其他活动失败）")
                        _emit_triple_progress(log_append=f"{dynamic_id}：失败")
                        for pending in future_to_id:
                            pending.cancel()
                        completed_summary = [
                            {
                                "dynamic_id": item["dynamic_id"],
                                "activity_title": item["activity_title"],
                                "lottery_type": item["lottery_type"],
                                "actions": [
                                    {
                                        "action": a.get("action"),
                                        "ok": a.get("ok"),
                                    }
                                    for a in (item["payload"].get("actions") or [])
                                ],
                            }
                            for item in results
                        ]
                        # 未完成但已开始执行的活动：外部副作用可能已发生，如实标记 partial
                        with progress_lock:
                            completed_ids = {str(item["dynamic_id"]) for item in completed_summary}
                            for target in targets:
                                did = str(target.get("dynamic_id") or "")
                                if did in completed_ids:
                                    continue
                                started = list(task_executed_actions.get(did) or [])
                                if not started:
                                    continue
                                completed_summary.append(
                                    {
                                        "dynamic_id": did,
                                        "activity_title": str(target.get("activity_title") or did),
                                        "lottery_type": str(target.get("lottery_type") or ""),
                                        "actions": [
                                            {"action": name, "ok": None, "partial": True}
                                            for name in started
                                        ],
                                        "partial": True,
                                    }
                                )
                        raise TripleParticipateFailed(
                            f"三连参与失败（{dynamic_id}）：{exc}",
                            completed=completed_summary,
                            failed_dynamic_id=dynamic_id,
                        ) from exc
            finally:
                if cancel_event and cancel_event.is_set():
                    _mark_other_tasks_stopped("", reason="已取消")
                    _emit_triple_progress()

        refresh_local_activity_statuses()
        results.sort(key=lambda item: target_ids.index(item["dynamic_id"]))
        log_blocks = [format_participation_log(item["payload"]) for item in results]
        message = f"三连参与完成：{len(results)} 个活动全部成功"
        progress(step=total_steps, total=total_steps, message=message, log_append=message)
        logger.info("三连参与成功 count=%s", len(results))
        invalidate_activity_cache()
        return {
            "ok": True,
            "message": message,
            "result": {
                "targets": [
                    {
                        "dynamic_id": item["dynamic_id"],
                        "activity_title": item["activity_title"],
                        "lottery_type": item["lottery_type"],
                    }
                    for item in results
                ],
                "items": [item["payload"] for item in results],
                "joined": len(results),
            },
            "log": "\n\n".join(log_blocks).strip(),
        }

    if action == "check_prize":
        # 中奖深检（@/回复/私信 + 关键词 + 推送；送达确认后才标记私信已读）
        from src.draw_check import _build_desp, check_prize_draw

        def on_step(step: int, total: int, message: str, **_kwargs: Any) -> None:
            progress(step=step, total=total, message=message)

        progress(step=1, total=2, message="正在深检未读消息…")
        with BilibiliClient() as client:
            result = check_prize_draw(client, push=bool(params.get("push", True)))
        total_hits = result["total"]
        delivered = result["delivered"]
        acknowledged = result["acknowledged"]
        if total_hits and not delivered:
            delivery_note = "，命中但通知未送达（私信保留未读）"
        elif delivered and not acknowledged:
            delivery_note = "，已推送但私信标记已读失败（可能重复提醒）"
        elif delivered:
            delivery_note = "，已推送通知"
        else:
            delivery_note = ""
        message = f"中奖深检完成：命中 {total_hits} 条{delivery_note}"
        progress(step=2, total=2, message=message)
        logger.info(
            "中奖深检 done total=%s delivered=%s acknowledged=%s",
            total_hits,
            delivered,
            acknowledged,
        )
        return {
            "ok": True,
            "message": message,
            "result": {
                "total": total_hits,
                "pushed": delivered,
                "delivered": delivered,
                "acknowledged": acknowledged,
                "at_count": len(result.get("at") or []),
                "reply_count": len(result.get("reply") or []),
                "dm_count": len(result.get("dm") or []),
                "send_result": result.get("send_result") or {},
            },
            "log": _build_desp(result).strip() or f"中奖深检完成：命中 {total_hits} 条",
        }

    if action == "clear_follows":
        # 清理动态 + 取关（源自 LAS clear）
        # 安全默认：dry_run=True，真实删除/取关必须由前端显式确认后传 dry_run=false
        from src.clear_follows import clear_follows

        def on_step(step: int, total: int, message: str, **_kwargs: Any) -> None:
            progress(step=step, total=total, message=message)

        dry_run = _parse_bool(params.get("dry_run"), default=True)
        progress(step=1, total=1, message="正在清理动态与关注…")
        with BilibiliClient() as client:
            result = clear_follows(
                client,
                max_days=int(params.get("max_days") or 30),
                delete_dynamic=_parse_bool(params.get("delete_dynamic"), default=True),
                white_list=str(params.get("white_list") or ""),
                dry_run=dry_run,
            )
        skipped_extra = ""
        if result.get("skipped_unowned"):
            skipped_extra += f"，跳过非 Binggo 转发 {result['skipped_unowned']} 条"
        if result.get("skipped_whitelist"):
            skipped_extra += f"，跳过白名单作者 {result['skipped_whitelist']} 条"
        message = (
            f"清理完成：删除动态 {result['deleted']} 条，取关 {result['unfollowed']} 人"
            f"{skipped_extra}"
            + ("（预演，未实际执行）" if dry_run else "")
        )
        progress(step=1, total=1, message=message)
        logger.info(
            "清理完成 deleted=%s unfollowed=%s skipped_unowned=%s skipped_whitelist=%s",
            result["deleted"],
            result["unfollowed"],
            result.get("skipped_unowned"),
            result.get("skipped_whitelist"),
        )
        return {
            "ok": True,
            "message": message,
            "result": result,
            "log": message,
        }

    raise ValueError(f"未知操作: {action}")
