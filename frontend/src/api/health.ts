// Ask the backend whether it is up; resolves to its status text, e.g. "ok".
export async function fetchHealth(): Promise<string> {
  const base = import.meta.env.VITE_API_BASE ?? "";
  const response = await fetch(`${base}/api/health`);
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  const body = (await response.json()) as { status: string };
  return body.status;
}
