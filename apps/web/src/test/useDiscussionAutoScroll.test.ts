import { describe, expect, it } from "vitest";

import { isNearBottom } from "../pages/useDiscussionAutoScroll";

describe("isNearBottom", () => {
  it("follows when the message pane is at its bottom", () => {
    expect(isNearBottom({ scrollHeight: 1200, scrollTop: 800, clientHeight: 400 })).toBe(true);
  });

  it("follows when the message pane is close to its bottom", () => {
    expect(isNearBottom({ scrollHeight: 1200, scrollTop: 720, clientHeight: 400 })).toBe(true);
  });

  it("does not follow after the user scrolls away from the bottom", () => {
    expect(isNearBottom({ scrollHeight: 1200, scrollTop: 640, clientHeight: 400 })).toBe(false);
  });
});
