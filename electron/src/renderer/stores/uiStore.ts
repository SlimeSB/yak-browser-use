import { _create } from './_factory';
import { readStorage, writeStorage } from '../utils/storage';

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

const initialTheme = readStorage<'dark' | 'light'>('theme', 'dark');
try { document.documentElement.setAttribute('data-theme', initialTheme); } catch { /* ok */ }

export const useUiStore = _create<UiState>((set) => ({
  activeTab: 'exec',
  theme: initialTheme,
  chatLayoutReversed: readStorage('chat-layout-reversed', false),
  sidebarCollapsed: readStorage('chat-sidebar-collapsed', false),
  setActiveTab: (tab) => set({ activeTab: tab }),
  setTheme: (t) => {
    set({ theme: t });
    writeStorage('theme', t);
    try { document.documentElement.setAttribute('data-theme', t); } catch { /* ok */ }
  },
  setChatLayoutReversed: (v) => {
    set({ chatLayoutReversed: v });
    writeStorage('chat-layout-reversed', v);
  },
  setSidebarCollapsed: (v) => {
    set({ sidebarCollapsed: v });
    writeStorage('chat-sidebar-collapsed', v);
  },
}));
