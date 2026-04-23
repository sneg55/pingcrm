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
