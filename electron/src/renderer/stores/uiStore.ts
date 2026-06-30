import { _create } from './_factory';

function _read<T>(key: string, fallback: T): T {
  try {
    const v = localStorage.getItem(key);
    if (v === null) return fallback;
    return JSON.parse(v) as T;
  } catch { return fallback; }
}

function _write(key: string, value: unknown) {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* ok */ }
}

interface UiState {
  activeTab: string;
  theme: 'dark' | 'light';
  chatLayoutReversed: boolean;
  sidebarCollapsed: boolean;
  setActiveTab: (tab: string) => void;
  setTheme: (t: 'dark' | 'light') => void;
  setChatLayoutReversed: (v: boolean) => void;
  setSidebarCollapsed: (v: boolean) => void;
}

const initialTheme = _read<'dark' | 'light'>('theme', 'dark');
try { document.documentElement.setAttribute('data-theme', initialTheme); } catch { /* ok */ }

export const useUiStore = _create<UiState>((set) => ({
  activeTab: 'exec',
  theme: initialTheme,
  chatLayoutReversed: _read('chat-layout-reversed', false),
  sidebarCollapsed: _read('chat-sidebar-collapsed', false),
  setActiveTab: (tab) => set({ activeTab: tab }),
  setTheme: (t) => {
    set({ theme: t });
    _write('theme', t);
    try { document.documentElement.setAttribute('data-theme', t); } catch { /* ok */ }
  },
  setChatLayoutReversed: (v) => {
    set({ chatLayoutReversed: v });
    _write('chat-layout-reversed', v);
  },
  setSidebarCollapsed: (v) => {
    set({ sidebarCollapsed: v });
    _write('chat-sidebar-collapsed', v);
  },
}));
