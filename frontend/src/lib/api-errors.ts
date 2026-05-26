// FastAPI returns { detail: string } for HTTPException and { detail: ValidationError[] }
// for 422 validation errors. openapi-fetch types only capture the 422 shape, so extract
// a display string from whatever came back.
export function extractErrorMessage(error: unknown): string | undefined {
  if (error == null || typeof error !== "object") return undefined;
  const detail: unknown = (error as { detail?: unknown }).detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail.length > 0) {
    const first: unknown = detail[0];
    if (first && typeof first === "object" && "msg" in first) {
      const msg = (first as { msg?: unknown }).msg;
      if (typeof msg === "string") return msg;
    }
  }
  return undefined;
}

export type ConflictingContact = {
  id: string;
  full_name?: string | null;
  given_name?: string | null;
  family_name?: string | null;
  emails?: string[] | null;
};

export type ApiError =
  | { kind: "plain"; message: string }
  | { kind: "conflict"; message: string; conflictingContact: ConflictingContact };

/**
 * Returns a conflict ApiError if `detail` is a well-formed conflict object
 * (non-null object with a non-null object `conflicting_contact`), otherwise null.
 */
function tryExtractConflict(detail: unknown): ApiError | null {
  if (detail == null || typeof detail !== "object" || Array.isArray(detail)) return null;
  if (!("conflicting_contact" in detail)) return null;
  const d = detail as { message?: unknown; conflicting_contact: unknown };
  if (d.conflicting_contact == null || typeof d.conflicting_contact !== "object") return null;
  return {
    kind: "conflict",
    message: typeof d.message === "string" ? d.message : "Conflict",
    conflictingContact: d.conflicting_contact as ConflictingContact,
  };
}

export function extractApiError(err: unknown): ApiError | null {
  if (err == null) return null;

  // FastAPI envelope: { detail: ... }
  if (typeof err === "object" && "detail" in err) {
    const detail = (err as { detail: unknown }).detail;

    // Structured conflict: { detail: { message, conflicting_contact } }
    const conflict = tryExtractConflict(detail);
    if (conflict) return conflict;

    // String detail
    if (typeof detail === "string") {
      return { kind: "plain", message: detail };
    }

    // Validation array
    if (Array.isArray(detail)) {
      const msg = detail
        .map((item) =>
          item != null && typeof item === "object" && "msg" in item
            ? String((item as { msg: unknown }).msg)
            : String(item)
        )
        .join("; ");
      return { kind: "plain", message: msg };
    }
  }

  // Generic Error
  if (err instanceof Error) {
    return { kind: "plain", message: err.message };
  }

  return { kind: "plain", message: "An unexpected error occurred" };
}
