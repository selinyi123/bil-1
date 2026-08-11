export type ConfigRecord = Record<string, unknown>;

function isRecord(value: unknown): value is ConfigRecord {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

/**
 * Merge form-owned fields into the last successfully loaded config.
 * Unknown/new backend fields survive older frontend form saves instead of being erased.
 */
export function mergeConfig(base: ConfigRecord | null | undefined, patch: ConfigRecord): ConfigRecord {
  const result: ConfigRecord = { ...(base || {}) };
  Object.entries(patch).forEach(([key, value]) => {
    const previous = result[key];
    if (isRecord(previous) && isRecord(value)) {
      result[key] = mergeConfig(previous, value);
    } else {
      result[key] = value;
    }
  });
  return result;
}

export interface AtUserInput {
  uid: number;
  name: string;
}

/** Strictly parse one `uid:昵称` per line; never silently save an entry the backend will ignore. */
export function parseAtUsers(raw: string): AtUserInput[] {
  const lines = String(raw || "")
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
  const users: AtUserInput[] = [];
  lines.forEach((line, index) => {
    const [uidPart, ...nameParts] = line.split(":");
    const uidText = String(uidPart || "").trim();
    const name = nameParts.join(":").trim();
    if (!/^\d+$/.test(uidText) || !name) {
      throw new Error(`@ 用户第 ${index + 1} 行格式无效，请填写 uid:昵称`);
    }
    const uid = Number(uidText);
    if (!Number.isSafeInteger(uid) || uid <= 0) {
      throw new Error(`@ 用户第 ${index + 1} 行 UID 无效`);
    }
    users.push({ uid, name });
  });
  return users;
}

export const DEFAULT_CLEANUP_PARTITION = "抽奖临时关注";

/** Mirror backend cleanup fallback so the confirmation UI names the actual partition. */
export function resolveCleanupPartitionName(config: ConfigRecord | null | undefined): string {
  const partition = isRecord(config?.partition) ? config!.partition as ConfigRecord : {};
  if (partition.enabled === true) {
    const name = String(partition.name || "").trim();
    if (name) return name;
  }
  return DEFAULT_CLEANUP_PARTITION;
}
