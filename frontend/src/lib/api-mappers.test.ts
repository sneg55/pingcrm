import { describe, expect, it } from "vitest";
import type { ContactCreateInput } from "@/hooks/use-contacts";
import { toContactCreateBody, toContactUpdateBody, toSuggestionUpdateBody, toOrgUpdateBody, type OrganizationUpdateInput } from "@/lib/api-mappers";

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

describe("toContactUpdateBody", () => {
  it("passes through a partial input unchanged", () => {
    const input: Partial<ContactCreateInput> = { full_name: "Ada Lovelace" };
    const body = toContactUpdateBody(input);
    expect(body).toEqual({ full_name: "Ada Lovelace" });
  });

  it("preserves empty array fields when explicitly provided", () => {
    const input: Partial<ContactCreateInput> = { emails: [], phones: [] };
    const body = toContactUpdateBody(input);
    expect(body.emails).toEqual([]);
    expect(body.phones).toEqual([]);
  });

  it("does not invent fields that were not provided", () => {
    const input: Partial<ContactCreateInput> = { priority_level: "high" };
    const body = toContactUpdateBody(input);
    expect("emails" in body).toBe(false);
    expect("phones" in body).toBe(false);
  });

  it("includes organization_id when provided (unlike create body)", () => {
    const input: Partial<ContactCreateInput> = { organization_id: "org-123" };
    const body = toContactUpdateBody(input);
    expect(body.organization_id).toBe("org-123");
  });
});

describe("toSuggestionUpdateBody", () => {
  it("requires status (compile-time) and passes it through", () => {
    const body = toSuggestionUpdateBody({ status: "sent" });
    expect(body.status).toBe("sent");
  });

  it("preserves optional fields when provided", () => {
    const body = toSuggestionUpdateBody({
      status: "snoozed",
      snooze_until: "2026-06-01T00:00:00Z",
      suggested_message: "Catch up soon?",
      suggested_channel: "email",
    });
    expect(body.snooze_until).toBe("2026-06-01T00:00:00Z");
    expect(body.suggested_message).toBe("Catch up soon?");
    expect(body.suggested_channel).toBe("email");
  });

  it("omits unset optional fields", () => {
    const body = toSuggestionUpdateBody({ status: "dismissed" });
    expect("snooze_until" in body).toBe(false);
    expect("suggested_message" in body).toBe(false);
    expect("suggested_channel" in body).toBe(false);
  });
});

describe("toOrgUpdateBody", () => {
  it("passes through whitelisted fields", () => {
    const input: OrganizationUpdateInput = {
      name: "Acme",
      domain: "acme.com",
      notes: "Big customer",
    };
    const body = toOrgUpdateBody(input);
    expect(body).toEqual({ name: "Acme", domain: "acme.com", notes: "Big customer" });
  });

  it("preserves null values (clearing a field)", () => {
    const input: OrganizationUpdateInput = { website: null };
    const body = toOrgUpdateBody(input);
    expect(body.website).toBeNull();
  });

  it("omits unset optional fields", () => {
    const input: OrganizationUpdateInput = { name: "Acme" };
    const body = toOrgUpdateBody(input);
    expect("domain" in body).toBe(false);
    expect("notes" in body).toBe(false);
  });
});
