const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

export async function apiGet<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`);
  if (!response.ok) {
    const payload = await safeJson(response);
    throw new Error(payload?.detail ?? `Request failed with status ${response.status}`);
  }
  return response.json();
}

export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify(body)
  });
  if (!response.ok) {
    const payload = await safeJson(response);
    throw new Error(payload?.detail ?? `Request failed with status ${response.status}`);
  }
  return response.json();
}

async function safeJson(response: Response): Promise<any> {
  try {
    return await response.json();
  } catch {
    return null;
  }
}

export function queryString(params: Record<string, string | number | null | undefined | string[]>) {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null || value === "") {
      return;
    }
    if (Array.isArray(value)) {
      value.forEach((item) => search.append(key, item));
      return;
    }
    search.set(key, String(value));
  });
  const output = search.toString();
  return output ? `?${output}` : "";
}

export function apiBaseUrl() {
  return API_BASE;
}
