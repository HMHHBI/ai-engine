/**
 * Parses and validates candidate document ID from URL query parameters.
 * Strict rules:
 * - Missing or empty -> null
 * - Non-numeric or floating point -> null
 * - <= 0 -> null
 * - Positive integer -> candidate document ID (still requires server-side validation)
 */
export function parseCandidateDocId(
  searchParams: URLSearchParams | { get: (key: string) => string | null } | null | undefined
): number | null {
  if (!searchParams) return null;

  const rawDocId = searchParams.get("docId");
  if (!rawDocId) return null;

  const trimmed = rawDocId.trim();
  if (!/^\d+$/.test(trimmed)) return null;

  const parsed = parseInt(trimmed, 10);
  if (Number.isNaN(parsed) || parsed <= 0 || !Number.isSafeInteger(parsed)) {
    return null;
  }

  return parsed;
}
