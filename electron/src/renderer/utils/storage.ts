
export function readStorage<T>(key: string, fallback: T): T {
  try {
    const v = localStorage.getItem(key);
    if (v === null) return fallback;
    return JSON.parse(v) as T;
  } catch { return fallback; }
}

export function writeStorage(key: string, value: unknown): void {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* ok */ }
}

export function removeStorage(key: string): void {
  try { localStorage.removeItem(key); } catch { /* ok */ }
}
