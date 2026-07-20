#!/usr/bin/env python3
"""One-shot: split web/static/app.js into web/frontend/src TypeScript modules.

Preserves logic; adds // @ts-nocheck on UI modules for strict-mode migration.
Re-run only when intentionally re-importing from the monolith.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_JS = ROOT / "web" / "static" / "app.js"
OUT = ROOT / "web" / "frontend" / "src"

# declaration name -> relative module path (under src/)
ASSIGN: dict[str, str] = {}

def assign_many(module: str, names: list[str]) -> None:
    for n in names:
        ASSIGN[n] = module


assign_many(
    "utils/text.ts",
    ["escapeHtml", "sanitizeUserText", "truncateText"],
)
assign_many(
    "utils/format.ts",
    [
        "formatUnixTimestamp",
        "formatWatchWindow",
        "formatWindowDays",
        "formatToastDetail",
        "formatLastParticipation",
        "formatHeat",
        "formatLotteryTime",
        "formatAccountStat",
        "formatJobProgressDisplay",
        "formatProgressTitle",
        "formatProgressDetail",
        "formatFilterSummary",
        "formatAutoCountdown",
        "badgeClass",
        "lotteryTypeTone",
        "activityStatusTone",
        "isLotterySoon",
    ],
)
assign_many(
    "utils/motion.ts",
    [
        "prefersReducedMotion",
        "setButtonLoading",
        "clearActionButtonLoading",
        "setSourceRowUpdating",
        "flashSourceRow",
        "pulseWatchSyncCard",
        "playSourcesEnter",
        "playActivitiesEnter",
        "pulseFilterSummary",
        "flashFilterPill",
        "playActivityListEnter",
        "playOverviewEnter",
        "flashButtonSuccess",
        "markSaveDirty",
        "clearSaveDirty",
        "animateStatValue",
        "highlightWatchUserChip",
        "flashActivityRows",
    ],
)
assign_many(
    "shell/toast.ts",
    ["showToast", "dismissRunningToasts", "setInlineFeedback", "TOAST_META"],
)
assign_many(
    "shell/confirm.ts",
    ["closeAppConfirm", "openAppConfirm", "confirmRefreshAll"],
)
assign_many(
    "shell/nav.ts",
    ["activateSection", "switchSection", "bindNavigation"],
)
assign_many(
    "shell/theme.ts",
    [
        "initSystemPreferences",
        "applySidebarCollapsed",
        "applyTheme",
        "SIDEBAR_ANIM_MS",
        "THEME_ANIM_MS",
    ],
)
assign_many(
    "account/index.ts",
    [
        "isLoggedIn",
        "isLlmConfigured",
        "isLlmTested",
        "isSetupComplete",
        "requireSetup",
        "renderSetupChecklist",
        "getAccountHeroTone",
        "renderAccountAvatar",
        "renderAccountAvatarWrap",
        "renderAccountStatusLabel",
        "isOnboardingDismissed",
        "dismissOnboarding",
        "getOnboardingCompletion",
        "countOnboardingDone",
        "getOnboardingCurrentIndex",
        "scrollToLlmSettings",
        "runOnboardingStepAction",
        "renderOnboardingPanel",
        "bindOnboardingPanel",
        "renderAtAlertBanner",
        "maybeShowAtUnreadAlert",
        "acknowledgeAtUnread",
        "bindAtAlertActions",
        "renderAccountViews",
        "loadAccount",
        "loadAccountExtras",
        "logoutAccount",
        "closeLogoutConfirmModal",
        "requestLogoutConfirm",
        "syncProjectState",
    ],
)
assign_many(
    "settings/index.ts",
    [
        "loadSettings",
        "getParticipateTextDefaults",
        "getParticipateTextForMode",
        "updateParticipateTextUI",
        "renderParticipateSettings",
        "saveParticipateTextMode",
        "bindParticipateSettings",
        "bindSettingsDirtyTracking",
        "getLlmFormValues",
        "renderLlmSettingsForm",
        "refreshLlmSettings",
        "saveLlmSettings",
        "testLlmSettings",
        "saveParticipateText",
        "resetParticipateText",
        "toggleLlmApiKeyVisibility",
        "bindLlmApiKeyToggle",
    ],
)
assign_many(
    "watch/index.ts",
    [
        "clearWatchMidError",
        "showWatchMidError",
        "closeWatchUserConfirm",
        "renderWatchUsersPanel",
        "updateWatchUserFormState",
        "loadWatchUsers",
        "parseWatchMidInput",
        "submitWatchUser",
        "removeWatchUser",
        "bindWatchUsers",
        "renderSources",
    ],
)
assign_many(
    "auto/index.ts",
    [
        "setAutoDockOpen",
        "getAutoCountdownSeconds",
        "toggleAutoDock",
        "resolveAutoSchedulerText",
        "resolveAutoJobText",
        "resolveAutoJobTone",
        "renderAutoPipeline",
        "updateAutoCollapsedMeta",
        "renderAutoDock",
        "tickAutoCountdown",
        "ensureAutoCountdown",
        "ensureAutoPolling",
        "stopAutoPolling",
        "fetchAutoStatus",
        "startAutoScheduler",
        "stopAutoScheduler",
        "bindAutoDock",
        "autoLogKey",
        "mergeAutoLogs",
    ],
)
assign_many(
    "activities/index.ts",
    [
        "buildActivityParticipateBtn",
        "buildActivityLastNote",
        "buildActivityLink",
        "renderActivityTableRow",
        "renderActivityCard",
        "renderActivities",
        "loadSummary",
        "setFilterPillGroup",
        "setStatusFilter",
        "setDrawWindowFilter",
        "updateDrawWindowHint",
        "buildActivityFilterQueryParams",
        "renderTripleParticipateBar",
        "buildActivityFilterJobParams",
        "getActiveFilterKey",
        "computeTripleTargetsFromItems",
        "resolveTripleTargets",
        "applyTripleTargets",
        "loadTripleTargets",
        "loadActivities",
        "bindFilterPills",
        "renderStats",
    ],
)
assign_many(
    "jobs/index.ts",
    [
        "isRefreshPipelineAction",
        "buildFailureContext",
        "classifyFailureText",
        "classifyJobFailure",
        "executeFailureAction",
        "renderFailureActions",
        "showFailureToast",
        "getQrcodeFocusable",
        "trapQrcodeFocus",
        "ensureQrcodeModalVisible",
        "loadQrcodeImage",
        "openQrcodeModalFresh",
        "resolveLoginPhase",
        "renderQrcodeLoginState",
        "hideQrcodeModal",
        "cancelLoginJob",
        "syncLogDockTone",
        "scrollJobLogToBottom",
        "setLogDockOpen",
        "toggleLogDock",
        "participateStepLabelsForType",
        "findTripleTargetForLane",
        "participateActiveStepIndex",
        "buildPipelineStepsHtml",
        "renderPipelineSteps",
        "buildJobKey",
        "resetJobProgressTracking",
        "parseTripleProgressLanes",
        "commentFailureOptional",
        "participationSucceeded",
        "payloadJoinedSuccess",
        "summarizeTripleResult",
        "renderActionChips",
        "classifyLaneStatus",
        "summarizeTripleProgressLanes",
        "hideParticipationResult",
        "scheduleParticipationResultDismiss",
        "restartParticipationResultProgress",
        "renderParticipationStepResults",
        "renderTripleParticipationResults",
        "showParticipationResult",
        "renderTripleParticipateProgress",
        "renderParticipateSteps",
        "refreshAllDataSourceCount",
        "refreshAllPipelinePhaseFromMessage",
        "refreshAllSubprogressRatio",
        "refreshAllPipelinePhase",
        "renderRefreshAllPipeline",
        "renderRefreshWatchPipeline",
        "calcJobProgressPercent",
        "setButtonsDisabled",
        "setProgressAria",
        "updateProgressUI",
        "updateJobUI",
        "startJob",
        "collectFinishedDynamicIds",
        "handleJobCompletion",
        "bindActionButtons",
        "resolveJobPollIntervalMs",
        "stopJobPolling",
        "applyRunningJobView",
        "finishJobOnce",
        "mergeJobProgress",
        "appendJobLogChunk",
        "startPolling",
    ],
)
assign_many(
    "realtime/sse.ts",
    [
        "markSseActive",
        "stopSseWatchdog",
        "startSseWatchdog",
        "closeEventSource",
        "fallbackToPolling",
        "handleSseMessage",
        "startRealtime",
        "SSE_WATCHDOG_MS",
        "SSE_RECONNECT_MS",
    ],
)
assign_many(
    "bootstrap.ts",
    ["init"],
)

# Top-level const/let that are not state / not in ASSIGN → dom.ts
DOM_MODULE = "dom.ts"


DECL_RE = re.compile(
    r"^(?P<export>export\s+)?(?P<kind>async\s+function|function|const|let|var)\s+(?P<name>[A-Za-z_$][\w$]*)"
)


def find_top_level_decls(lines: list[str]) -> list[tuple[int, int, str, str]]:
    """Return list of (start, end_exclusive, name, kind) for top-level declarations."""
    decls: list[tuple[int, int, str, str]] = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        if line.startswith(" ") or line.startswith("\t") or not line.strip():
            i += 1
            continue
        m = DECL_RE.match(line)
        if not m:
            # top-level statements (addEventListener etc.) — collect later
            i += 1
            continue
        name = m.group("name")
        kind = m.group("kind")
        start = i
        if kind.startswith("function") or kind.startswith("async"):
            # brace match
            depth = 0
            started = False
            j = i
            while j < n:
                for ch in lines[j]:
                    if ch == "{":
                        depth += 1
                        started = True
                    elif ch == "}":
                        depth -= 1
                if started and depth == 0:
                    j += 1
                    break
                j += 1
            decls.append((start, j, name, kind))
            i = j
            continue
        # const/let — object/array/arrow may span lines
        j = i
        depth_brace = 0
        depth_paren = 0
        depth_bracket = 0
        while j < n:
            s = lines[j]
            # strip strings roughly for brace counting — good enough for this file
            for ch in s:
                if ch == "{":
                    depth_brace += 1
                elif ch == "}":
                    depth_brace -= 1
                elif ch == "(":
                    depth_paren += 1
                elif ch == ")":
                    depth_paren -= 1
                elif ch == "[":
                    depth_bracket += 1
                elif ch == "]":
                    depth_bracket -= 1
            # end when statement completes at depth 0 and line has ; or ends assignment block
            if depth_brace <= 0 and depth_paren <= 0 and depth_bracket <= 0:
                # const x = ...; or multi-line ending with };
                if ";" in s or (j > i and s.rstrip().endswith("}")) or s.rstrip().endswith("];"):
                    j += 1
                    break
                # single-line without semicolon (rare)
                if j == i and ("=" in s) and not s.rstrip().endswith(",") and not s.rstrip().endswith("{") and not s.rstrip().endswith("("):
                    j += 1
                    break
            j += 1
        decls.append((start, j, name, kind))
        i = j
    return decls


def module_for(name: str) -> str:
    if name == "state":
        return "state.ts"
    if name in ASSIGN:
        return ASSIGN[name]
    return DOM_MODULE


def transform_decl_lines(lines: list[str], kind: str) -> list[str]:
    out = list(lines)
    first = out[0]
    if first.startswith("export "):
        return out
    if kind.startswith("function") or kind.startswith("async"):
        out[0] = "export " + first
    elif kind in ("const", "let", "var"):
        out[0] = "export " + first
    return out


def collect_side_effects(lines: list[str], decl_spans: list[tuple[int, int, str, str]]) -> list[tuple[int, int]]:
    covered = set()
    for a, b, _, _ in decl_spans:
        for i in range(a, b):
            covered.add(i)
    spans: list[tuple[int, int]] = []
    i = 0
    n = len(lines)
    while i < n:
        if i in covered or not lines[i].strip():
            i += 1
            continue
        # skip pure comments blocks at top level that sit between decls — attach to bootstrap
        start = i
        while i < n and i not in covered:
            i += 1
        # trim trailing blank from span content later
        spans.append((start, i))
    return spans


def rel_import(from_mod: str, to_mod: str) -> str:
    """Return path for import from from_mod to to_mod (both under src/)."""
    if from_mod == to_mod:
        return ""
    from_parts = Path(from_mod).parts
    to_path = Path(to_mod)
    # strip .ts
    to_no_ext = to_path.with_suffix("")
    depth = len(from_parts) - 1
    prefix = "/".join([".."] * depth) if depth else "."
    target = f"{prefix}/{to_no_ext.as_posix()}"
    if not target.startswith("."):
        target = "./" + target
    return target


def main() -> None:
    text = SRC_JS.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    # normalize to \n only in memory
    raw_lines = text.splitlines()
    decls = find_top_level_decls(raw_lines)
    print(f"Found {len(decls)} top-level declarations")

    # Group decl bodies by module
    modules: dict[str, list[str]] = {}
    name_to_module: dict[str, str] = {}
    for start, end, name, kind in decls:
        mod = module_for(name)
        name_to_module[name] = mod
        body = transform_decl_lines(raw_lines[start:end], kind)
        modules.setdefault(mod, []).extend(body)
        modules[mod].append("")  # blank line between decls

    # Side-effect statements → bootstrap.ts
    side_spans = collect_side_effects(raw_lines, decls)
    side_lines: list[str] = []
    for a, b in side_spans:
        chunk = raw_lines[a:b]
        # skip if only comments/blank
        if not any(x.strip() and not x.strip().startswith("//") for x in chunk):
            continue
        side_lines.extend(chunk)
        side_lines.append("")
    if side_lines:
        modules.setdefault("bootstrap.ts", []).extend(side_lines)

    # All exported names
    all_names = sorted(name_to_module.keys())

    # For each module, detect referenced names from other modules
    ident_re = re.compile(r"\b([A-Za-z_$][\w$]*)\b")

    def needed_imports(mod: str, body_lines: list[str]) -> dict[str, set[str]]:
        """module -> set of names"""
        own = {n for n, m in name_to_module.items() if m == mod}
        text_body = "\n".join(body_lines)
        found = set(ident_re.findall(text_body))
        imports: dict[str, set[str]] = {}
        for name in found:
            if name in own:
                continue
            if name not in name_to_module:
                continue
            other = name_to_module[name]
            if other == mod:
                continue
            imports.setdefault(other, set()).add(name)
        return imports

    # Write state.ts specially typed
    state_body = modules.pop("state.ts", None)
    OUT.mkdir(parents=True, exist_ok=True)

    # api/client is hand-written — remove fetchJSON from dom if present
    if "fetchJSON" in name_to_module:
        # remove fetchJSON from whatever module it landed in
        fj_mod = name_to_module["fetchJSON"]
        if fj_mod in modules:
            # strip fetchJSON function from that module
            modules[fj_mod] = strip_named_function(modules[fj_mod], "fetchJSON")
        name_to_module["fetchJSON"] = "api/client.ts"

    for mod, body in modules.items():
        imports_map = needed_imports(mod, body)
        # always need state if referenced
        header: list[str] = [
            "// @ts-nocheck",
            "/* eslint-disable */",
            "/** Migrated from web/static/app.js — logic preserved. */",
            "",
        ]
        # import state
        if "state" in "\n".join(body) or any(
            n in "\n".join(body) for n in ("state.", "state ")
        ):
            # check identifier state
            if re.search(r"\bstate\b", "\n".join(body)):
                path = rel_import(mod, "state.ts")
                header.append(f'import {{ state }} from "{path}";')
        if re.search(r"\bfetchJSON\b", "\n".join(body)):
            path = rel_import(mod, "api/client.ts")
            header.append(f'import {{ fetchJSON }} from "{path}";')

        for other_mod, names in sorted(imports_map.items()):
            if other_mod == "api/client.ts":
                continue  # handled
            if other_mod == "state.ts":
                continue
            path = rel_import(mod, other_mod)
            named = ", ".join(sorted(names))
            header.append(f'import {{ {named} }} from "{path}";')

        header.append("")
        content = "\n".join(header + body).rstrip() + "\n"
        out_path = OUT / mod
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(content, encoding="utf-8")
        print(f"Wrote {out_path.relative_to(ROOT)} ({len(body)} lines)")

    # state.ts hand-shaped
    write_state_ts(OUT / "state.ts", state_body)
    write_types(OUT / "types" / "index.ts")
    write_api_client(OUT / "api" / "client.ts")
    write_main(OUT / "main.ts")
    print("Done.")


def strip_named_function(lines: list[str], name: str) -> list[str]:
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if re.match(rf"^export\s+(async\s+)?function\s+{name}\b", line) or re.match(
            rf"^(async\s+)?function\s+{name}\b", line
        ):
            depth = 0
            started = False
            while i < len(lines):
                for ch in lines[i]:
                    if ch == "{":
                        depth += 1
                        started = True
                    elif ch == "}":
                        depth -= 1
                i += 1
                if started and depth == 0:
                    break
            # skip following blank
            while i < len(lines) and not lines[i].strip():
                i += 1
            continue
        out.append(line)
        i += 1
    return out


def write_state_ts(path: Path, _body: list[str] | None) -> None:
    path.write_text(
        '''import type { AppState } from "./types";

export const state: AppState = {
  page: 1,
  pageSize: 20,
  filters: { q: "", type: "", status: "", draw: "", drawWindow: "", sort: "", order: "" },
  polling: null,
  logDockOpen: false,
  autoDockOpen: false,
  autoScheduler: null,
  autoPollTimer: null,
  autoCountdownTimer: null,
  autoServerSkewMs: 0,
  autoLogs: [],
  qrcodeDismissed: false,
  lastQrcodeRefresh: 0,
  account: null,
  settings: null,
  atAlertShownKey: "",
  tripleTargets: { count: 0, limit: 3, items: [] },
  tripleFilterKey: "",
  smoothJobPercent: 0,
  activeJobKey: "",
  jobResultTimer: null,
  watchUsers: null,
  lastJobAttempt: null,
  onboardingCelebrating: false,
  statValues: {},
  currentJob: null,
  eventSource: null,
  sseHealthy: false,
  sseLastActive: 0,
  sseWatchdog: null,
  sseReconnectTimer: null,
  lastFinishedJobKey: "",
};
''',
        encoding="utf-8",
    )
    print(f"Wrote {path.relative_to(ROOT)}")


def write_types(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        '''export type JobState = "idle" | "running" | "success" | "error" | "cancelled" | string;

export interface JobStatus {
  id?: number | string | null;
  state?: JobState;
  action?: string;
  label?: string;
  source?: string;
  message?: string;
  progress_step?: number;
  progress_total?: number;
  progress_message?: string;
  log?: string;
  result?: Record<string, unknown> | null;
  finished_at?: string | null;
  [key: string]: unknown;
}

export interface ApiErrorFields {
  code?: string;
  httpStatus?: number;
  detail?: unknown;
}

export type ApiError = Error & ApiErrorFields;

export interface AutoStatus {
  state?: string;
  next_slot?: number | null;
  server_now?: number | null;
  logs?: Array<Record<string, unknown>>;
  pipeline?: unknown;
  current_job?: JobStatus | null;
  [key: string]: unknown;
}

export interface AppFilters {
  q: string;
  type: string;
  status: string;
  draw: string;
  drawWindow: string;
  sort: string;
  order: string;
}

export interface AppState {
  page: number;
  pageSize: number;
  filters: AppFilters;
  polling: number | null;
  logDockOpen: boolean;
  autoDockOpen: boolean;
  autoScheduler: AutoStatus | null;
  autoPollTimer: number | null;
  autoCountdownTimer: number | null;
  autoServerSkewMs: number;
  autoLogs: Array<Record<string, unknown>>;
  qrcodeDismissed: boolean;
  lastQrcodeRefresh: number;
  account: Record<string, unknown> | null;
  settings: Record<string, unknown> | null;
  atAlertShownKey: string;
  tripleTargets: { count: number; limit: number; items: unknown[] };
  tripleFilterKey: string;
  smoothJobPercent: number;
  activeJobKey: string;
  jobResultTimer: number | null;
  watchUsers: Record<string, unknown> | null;
  lastJobAttempt: Record<string, unknown> | null;
  onboardingCelebrating: boolean;
  statValues: Record<string, number>;
  currentJob: JobStatus | null;
  eventSource: EventSource | null;
  sseHealthy: boolean;
  sseLastActive: number;
  sseWatchdog: number | null;
  sseReconnectTimer: number | null;
  lastFinishedJobKey: string;
}
''',
        encoding="utf-8",
    )
    print(f"Wrote {path.relative_to(ROOT)}")


def write_api_client(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        '''import type { ApiError } from "../types";

export type FetchJSONOptions = RequestInit & {
  timeoutMs?: number;
};

/** Parse API error payload (contract v1 dual-read). Exported for tests. */
export function parseApiErrorPayload(
  text: string,
  statusText: string,
): { message: string; code: string; detail: unknown } {
  let message = text || statusText;
  let code = "";
  let detail: unknown = null;
  try {
    const payload = JSON.parse(text);
    const errObj = payload?.error;
    if (errObj && typeof errObj === "object") {
      if (errObj.message) message = String(errObj.message);
      code = String(errObj.code || "");
      detail = errObj.detail ?? null;
    } else if (typeof payload?.detail === "string") {
      message = payload.detail;
    } else if (Array.isArray(payload?.detail)) {
      message = "请求参数无效";
      detail = payload.detail;
    }
  } catch {
    // 非 JSON 响应，保留原始文本
  }
  return { message, code, detail };
}

export async function fetchJSON<T = unknown>(
  url: string,
  options: FetchJSONOptions = {},
): Promise<T> {
  const { timeoutMs = 30000, ...fetchOptions } = options;
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, {
      cache: "no-store",
      ...fetchOptions,
      signal: controller.signal,
    });
    if (!response.ok) {
      const text = await response.text();
      const { message, code, detail } = parseApiErrorPayload(text, response.statusText);
      const error = new Error(message) as ApiError;
      error.code = code;
      error.httpStatus = response.status;
      error.detail = detail;
      throw error;
    }
    return response.json() as Promise<T>;
  } catch (error) {
    if (error instanceof Error && error.name === "AbortError") {
      throw new Error("请求超时，请稍后重试");
    }
    throw error;
  } finally {
    window.clearTimeout(timer);
  }
}
''',
        encoding="utf-8",
    )
    print(f"Wrote {path.relative_to(ROOT)}")


def write_main(path: Path) -> None:
    path.write_text(
        '''import "./styles/styles.css";
import { init } from "./bootstrap";
import { showToast } from "./shell/toast";

init().catch((error: unknown) => {
  const message = error instanceof Error ? error.message : String(error);
  showToast(String(message || error), "error");
});
''',
        encoding="utf-8",
    )
    print(f"Wrote {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
