/**
 * Client-side error reporter — sends dashboard errors to the server
 * so they appear in journalctl logs and are visible for troubleshooting.
 *
 * Fire-and-forget: never throws, never blocks the UI.
 */

export function reportDashboardError(
  source: string,
  message: string,
  details?: Record<string, unknown>
) {
  try {
    fetch("/api/dashboard/error", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ source, message, details }),
    }).catch(() => {
      // Truly fire-and-forget — if the error endpoint is down, don't cascade
    });
  } catch {
    // Defensive — should never happen but don't let error reporting cause errors
  }
}
