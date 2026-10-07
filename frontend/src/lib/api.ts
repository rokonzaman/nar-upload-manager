/** API client: fetch wrapper with JWT auth, typed helpers, upload progress. */

let _apiUrl: string | null = null;
let _apiUrlPromise: Promise<string> | null = null;

async function getApiUrl(): Promise<string> {
  if (_apiUrl) return _apiUrl;
  if (!_apiUrlPromise) {
    _apiUrlPromise = fetch("/api/runtime-config")
      .then((r): Promise<{ apiUrl?: string }> => r.json())
      .then((data) => {
        _apiUrl = data.apiUrl ?? "http://localhost:8000";
        return _apiUrl;
      })
      .catch(() => {
        _apiUrl = "http://localhost:8000";
        return _apiUrl;
      });
  }
  return _apiUrlPromise;
}

const TOKEN_KEY = "nar_token";
const USER_KEY = "nar_user";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function setSession(token: string, user: unknown): void {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

export function clearSession(): void {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

export function getStoredUser<T>(): T | null {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
}

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

function redirectToLogin(): void {
  if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
    clearSession();
    window.location.href = "/login";
  }
}

async function request<T>(
  method: string,
  path: string,
  options: { body?: unknown; params?: Record<string, string | number | boolean | undefined> } = {},
): Promise<T> {
  const baseUrl = await getApiUrl();
  const url = new URL(`${baseUrl}/api/v1${path}`);
  for (const [key, value] of Object.entries(options.params ?? {})) {
    if (value !== undefined && value !== null && value !== "") {
      url.searchParams.set(key, String(value));
    }
  }
  const headers: Record<string, string> = {};
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  if (options.body !== undefined) headers["Content-Type"] = "application/json";

  const response = await fetch(url.toString(), {
    method,
    headers,
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
  });

  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const data = await response.json();
      if (typeof data?.detail === "string") message = data.detail;
    } catch {
      /* keep default message */
    }
    if (response.status === 401 && !window.location.pathname.startsWith("/login")) {
      redirectToLogin();
    }
    throw new ApiError(response.status, message);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  get: <T>(path: string, params?: Record<string, string | number | boolean | undefined>) =>
    request<T>("GET", path, { params }),
  post: <T>(path: string, body?: unknown, params?: Record<string, string | number | boolean | undefined>) =>
    request<T>("POST", path, { body, params }),
  put: <T>(path: string, body?: unknown) => request<T>("PUT", path, { body }),
  del: <T>(path: string, body?: unknown) => request<T>("DELETE", path, { body }),
};

/** Upload files with per-request progress callback (XMLHttpRequest). */
export function uploadFiles(
  path: string,
  files: File[],
  params: Record<string, string>,
  onProgress: (percent: number) => void,
): Promise<import("./types").UploadResult[]> {
  return new Promise((resolve, reject) => {
    getApiUrl().then((baseUrl) => {
      const url = new URL(`${baseUrl}/api/v1${path}`);
      for (const [key, value] of Object.entries(params)) url.searchParams.set(key, value);

      const xhr = new XMLHttpRequest();
      xhr.open("POST", url.toString());
      const token = getToken();
      if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);

      xhr.upload.onprogress = (event) => {
        if (event.lengthComputable) onProgress(Math.round((event.loaded / event.total) * 100));
      };
      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          resolve(JSON.parse(xhr.responseText));
        } else if (xhr.status === 401) {
          redirectToLogin();
          reject(new ApiError(401, "Unauthorized"));
        } else {
          let message = `Upload failed (${xhr.status})`;
          try {
            message = JSON.parse(xhr.responseText)?.detail ?? message;
          } catch {
            /* ignore */
          }
          reject(new ApiError(xhr.status, message));
        }
      };
      xhr.onerror = () => reject(new ApiError(0, "Network error during upload"));

      const form = new FormData();
      for (const file of files) form.append("files", file);
      xhr.send(form);
    });
  });
}

/** Download a file (blob) with auth header and trigger a browser save. */
export async function downloadFile(path: string, filename: string): Promise<void> {
  const baseUrl = await getApiUrl();
  const response = await fetch(`${baseUrl}/api/v1${path}`, {
    headers: getToken() ? { Authorization: `Bearer ${getToken()}` } : {},
  });
  if (!response.ok) throw new ApiError(response.status, `Download failed (${response.status})`);
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}
