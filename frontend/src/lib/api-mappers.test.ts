import { describe, expect, it } from "vitest";
import type { ContactCreateInput } from "@/hooks/use-contacts";
import { toContactCreateBody } from "@/lib/api-mappers";

describe("toContactCreateBody", () => {
  it("defaults missing emails and phones to empty arrays", () => {
    const input: ContactCreateInput = { full_name: "Ada Lovelace" };
    const body = toContactCreateBody(input);
    expect(body.emails).toEqual([]);
    expect(body.phones).toEqual([]);
    expect(body.full_name).toBe("Ada Lovelace");
  });

  it("preserves provided emails and phones", () => {
    const input: ContactCreateInput = {
      emails: ["a@b.co"],
      phones: ["+1234"],
    };
    const body = toContactCreateBody(input);
    expect(body.emails).toEqual(["a@b.co"]);
    expect(body.phones).toEqual(["+1234"]);
  });

  it("passes through other optional fields unchanged", () => {
    const input: ContactCreateInput = {
      twitter_handle: "ada",
      title: "Mathematician",
    };
    const body = toContactCreateBody(input);
    expect(body.twitter_handle).toBe("ada");
    expect(body.title).toBe("Mathematician");
  });

  it("strips organization_id (not part of ContactCreate schema)", () => {
    const input: ContactCreateInput = {
      full_name: "Ada",
      organization_id: "org-123",
    };
    const body = toContactCreateBody(input);
    expect("organization_id" in body).toBe(false);
  });

  it("defaults missing tags to [] and priority_level to 'medium'", () => {
    const input: ContactCreateInput = { full_name: "Ada" };
    const body = toContactCreateBody(input);
    expect(body.tags).toEqual([]);
    expect(body.priority_level).toBe("medium");
  });

  it("preserves provided tags and priority_level", () => {
    const input: ContactCreateInput = {
      tags: ["friend", "work"],
      priority_level: "high",
    };
    const body = toContactCreateBody(input);
    expect(body.tags).toEqual(["friend", "work"]);
    expect(body.priority_level).toBe("high");
  });
});
