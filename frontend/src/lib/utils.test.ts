import { describe, it, expect } from "vitest";
import { cn } from "./utils";

describe("cn", () => {
  it("merges class names", () => {
    expect(cn("foo", "bar")).toBe("foo bar");
  });

  it("handles conditional classes", () => {
    expect(cn("base", false && "hidden", "visible")).toBe("base visible");
  });

  it("handles undefined and null", () => {
    expect(cn("base", undefined, null, "end")).toBe("base end");
  });

  it("merges tailwind classes correctly", () => {
    expect(cn("px-4", "px-2")).toBe("px-2");
  });

  it("handles empty input", () => {
    expect(cn()).toBe("");
  });

  it("handles arrays", () => {
    expect(cn(["foo", "bar"])).toBe("foo bar");
  });
});
