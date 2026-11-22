/** Accept only a trusted build-time mount path on this origin. */
export function jaegerMountPath(value: unknown): string | null {
  if (typeof value !== "string" || value.length > 256 || value !== value.trim()) return null;
  if (!/^\/[A-Za-z0-9_-]+(?:\/[A-Za-z0-9_-]+)*\/?$/.test(value)) return null;
  return value.replace(/\/$/, "");
}

export function validTraceIds(values: unknown): string[] {
  if (!Array.isArray(values)) return [];
  return [...new Set(values.filter((id): id is string =>
    typeof id === "string" && id.length === 32 && /^[0-9a-f]+$/.test(id) && !/^0+$/.test(id)))];
}
