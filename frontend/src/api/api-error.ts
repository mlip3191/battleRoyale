// An HTTP error from our backend; `status` lets callers tell "not found" from a passing hiccup,
// and `detail` carries the server's own plain-language message when it sent one.
// It lives on its own so fixtures.ts can throw it without importing client.ts (which imports fixtures.ts).
export class ApiError extends Error {
  status: number;
  detail: string | null;
  constructor(status: number, detail: string | null = null) {
    super(`HTTP ${status}`);
    this.status = status;
    this.detail = detail;
  }
}
