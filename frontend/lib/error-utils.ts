/**
 * Normalizes backend error details into a user-friendly string.
 * Handles FastAPI/Pydantic validation errors which can be:
 * - A string
 * - An array of validation error objects with {type, loc, msg, input, ctx}
 * - Other objects
 */
export function normalizeErrorDetail(detail: unknown, fallback: string): string {
  if (typeof detail === "string") {
    return detail
  }
  if (Array.isArray(detail)) {
    // FastAPI/Pydantic validation errors are usually arrays of {loc, msg, type, ctx}
    return detail.map((d: any) => d?.msg ?? JSON.stringify(d)).join("; ")
  }
  return fallback
}

