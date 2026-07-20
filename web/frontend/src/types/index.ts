export type JobState = "idle" | "running" | "success" | "error" | "cancelled" | string;

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
