import { describe, expect, it } from "vitest";
import { mergeConfig, parseAtUsers, resolveCleanupPartitionName } from "./config";

describe("extra config contract helpers", () => {
  it("preserves unknown backend fields on form merge", () => {
    const merged = mergeConfig(
      {
        enabled: true,
        future_field: { keep: "yes", nested: 1 },
        channels: { telegram: { bot_token: "****", future_token_mode: "v2" } },
      },
      {
        enabled: false,
        channels: { telegram: { chat_id: "123" } },
      },
    );
    expect(merged).toEqual({
      enabled: false,
      future_field: { keep: "yes", nested: 1 },
      channels: {
        telegram: {
          bot_token: "****",
          future_token_mode: "v2",
          chat_id: "123",
        },
      },
    });
  });

  it("requires uid:name instead of silently accepting an unusable @ entry", () => {
    expect(parseAtUsers("294887687:转发抽奖娘")).toEqual([
      { uid: 294887687, name: "转发抽奖娘" },
    ]);
    expect(() => parseAtUsers("294887687")).toThrow(/uid:昵称/);
    expect(() => parseAtUsers("abc:昵称")).toThrow(/uid:昵称/);
  });

  it("shows the same cleanup partition the backend will use", () => {
    expect(
      resolveCleanupPartitionName({ partition: { enabled: true, name: "我的抽奖关注" } }),
    ).toBe("我的抽奖关注");
    expect(
      resolveCleanupPartitionName({ partition: { enabled: false, name: "不会使用" } }),
    ).toBe("抽奖临时关注");
  });
});
