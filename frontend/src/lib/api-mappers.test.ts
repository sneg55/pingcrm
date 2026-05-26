import { describe, expect, it } from "vitest";
import type { ContactCreateInput } from "@/hooks/use-contacts";
import { toContactCreateBody } from "./api-mappers";

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
});
