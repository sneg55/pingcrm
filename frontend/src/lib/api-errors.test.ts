import { describe, it, expect } from "vitest";
import { extractErrorMessage } from "./api-errors";
import { extractApiError, type ConflictingContact } from "./api-errors";

describe("extractErrorMessage", () => {
  describe("non-object inputs return undefined", () => {
    it("returns undefined for null", () => {
      expect(extractErrorMessage(null)).toBeUndefined();
    });

    it("returns undefined for undefined", () => {
      expect(extractErrorMessage(undefined)).toBeUndefined();
    });

    it("returns undefined for a string", () => {
      expect(extractErrorMessage("oops")).toBeUndefined();
    });

    it("returns undefined for a number", () => {
      expect(extractErrorMessage(42)).toBeUndefined();
    });

    it("returns undefined for a boolean", () => {
      expect(extractErrorMessage(true)).toBeUndefined();
      expect(extractErrorMessage(false)).toBeUndefined();
    });

    it("returns undefined for an empty object", () => {
      expect(extractErrorMessage({})).toBeUndefined();
    });
  });

  describe("FastAPI HTTPException shape (detail: string)", () => {
    it("returns the detail string directly", () => {
      expect(extractErrorMessage({ detail: "Not found" })).toBe("Not found");
    });

    it("returns an empty string detail unchanged", () => {
      expect(extractErrorMessage({ detail: "" })).toBe("");
    });
  });

  describe("FastAPI 422 validation array (detail: ValidationError[])", () => {
    it("returns the first item's msg", () => {
      const err = {
        detail: [
          { loc: ["body", "name"], msg: "field required", type: "value_error.missing" },
          { loc: ["body", "email"], msg: "value is not a valid email", type: "value_error.email" },
        ],
      };
      expect(extractErrorMessage(err)).toBe("field required");
    });

    it("returns undefined for empty detail array", () => {
      expect(extractErrorMessage({ detail: [] })).toBeUndefined();
    });

    it("returns undefined when first item is not an object (string)", () => {
      expect(extractErrorMessage({ detail: ["not an object"] })).toBeUndefined();
    });

    it("returns undefined when first item is not an object (number)", () => {
      expect(extractErrorMessage({ detail: [123] })).toBeUndefined();
    });

    it("returns undefined when first item is null", () => {
      expect(extractErrorMessage({ detail: [null] })).toBeUndefined();
    });

    it("returns undefined when first item is missing msg", () => {
      expect(extractErrorMessage({ detail: [{ loc: ["body"], type: "x" }] })).toBeUndefined();
    });

    it("returns undefined when first item has non-string msg (number)", () => {
      expect(extractErrorMessage({ detail: [{ msg: 999 }] })).toBeUndefined();
    });

    it("returns undefined when first item has non-string msg (null)", () => {
      expect(extractErrorMessage({ detail: [{ msg: null }] })).toBeUndefined();
    });

    it("returns undefined when first item has non-string msg (object)", () => {
      expect(extractErrorMessage({ detail: [{ msg: { nested: "x" } }] })).toBeUndefined();
    });
  });

  describe("other detail shapes return undefined", () => {
    it("returns undefined when detail is null", () => {
      expect(extractErrorMessage({ detail: null })).toBeUndefined();
    });

    it("returns undefined when detail is a number", () => {
      expect(extractErrorMessage({ detail: 500 })).toBeUndefined();
    });

    it("returns undefined when detail is an object (not array, not string)", () => {
      expect(extractErrorMessage({ detail: { code: "ERR" } })).toBeUndefined();
    });
  });
});

describe("extractApiError", () => {
  it("returns null for nullish input", () => {
    expect(extractApiError(null)).toBeNull();
    expect(extractApiError(undefined)).toBeNull();
  });

  it("returns a plain error for FastAPI string detail", () => {
    const result = extractApiError({ detail: "Contact not found" });
    expect(result).toEqual({ kind: "plain", message: "Contact not found" });
  });

  it("returns a plain error for FastAPI validation detail", () => {
    const result = extractApiError({
      detail: [{ loc: ["body", "emails"], msg: "field required", type: "value_error.missing" }],
    });
    expect(result?.kind).toBe("plain");
    expect(result?.message).toContain("field required");
  });

  it("returns a conflict error when detail includes conflicting_contact", () => {
    const conflictingContact: ConflictingContact = {
      id: "abc-123",
      full_name: "Ada Lovelace",
    };
    const result = extractApiError({
      detail: {
        message: "Email already used by another contact",
        conflicting_contact: conflictingContact,
      },
    });
    expect(result).toEqual({
      kind: "conflict",
      message: "Email already used by another contact",
      conflictingContact,
    });
  });

  it("returns a plain error for unknown error shapes", () => {
    const result = extractApiError({ some: "weird shape" });
    expect(result?.kind).toBe("plain");
  });

  it("returns a plain error for Error instances", () => {
    const result = extractApiError(new Error("Boom"));
    expect(result).toEqual({ kind: "plain", message: "Boom" });
  });

  it("falls back to plain when conflicting_contact is null (malformed payload)", () => {
    const result = extractApiError({ detail: { conflicting_contact: null } });
    // Should not return kind: 'conflict' with a null conflictingContact (type unsafe).
    // Fall through to fallback.
    expect(result?.kind).toBe("plain");
  });
});
