export const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

const TOKEN_KEY = "fa_session_token";

export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

export function getToken() {
  try {
    return localStorage.getItem(TOKEN_KEY) || "";
  } catch {
    return "";
  }
}

export function setToken(value) {
  try {
    if (value) localStorage.setItem(TOKEN_KEY, value);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage unavailable: the session still works for this tab */
  }
}

async function errorFrom(response) {
  let detail = "";
  try {
    const body = await response.json();
    detail = typeof body.detail === "string" ? body.detail : "";
  } catch {
    /* body was not JSON */
  }
  if (response.status === 401) return new ApiError(401, detail || "Your session has expired. Sign in again.");
  if (response.status === 409) return new ApiError(409, detail || "That conflicts with something already saved.");
  if (response.status === 429) return new ApiError(429, detail || "Too many requests. Wait a minute and try again.");
  return new ApiError(response.status, detail || `Request failed (${response.status}).`);
}

/** JSON request against the backend. The stored session token is attached automatically. */
export async function api(path, { method = "GET", body, token = getToken(), signal } = {}) {
  let response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      method,
      headers: {
        ...(body ? { "Content-Type": "application/json" } : {}),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: body ? JSON.stringify(body) : undefined,
      signal,
    });
  } catch (err) {
    if (err?.name === "AbortError") throw err;
    throw new ApiError(0, "Could not reach the server. Check that the backend is running.");
  }
  if (!response.ok) throw await errorFrom(response);
  if (response.status === 204) return null;
  return response.json();
}

/**
 * POST /analyze and stream NDJSON events into `onEvent`:
 * {type:"token"|"tool_call"|"error"|"done", ...}
 */
export async function streamAnalyze(payload, { onEvent, signal } = {}) {
  let response;
  try {
    response = await fetch(`${API_URL}/analyze`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${getToken()}`,
      },
      body: JSON.stringify(payload),
      signal,
    });
  } catch (err) {
    if (err?.name === "AbortError") throw err;
    throw new ApiError(0, "Could not reach the server. Check that the backend is running.");
  }
  if (!response.ok) throw await errorFrom(response);

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";
    for (const line of lines) {
      if (!line.trim()) continue;
      try {
        onEvent(JSON.parse(line));
      } catch {
        /* skip malformed line */
      }
    }
  }
}
