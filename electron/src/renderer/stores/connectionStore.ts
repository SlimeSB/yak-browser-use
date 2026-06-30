import { _create } from './_factory';
import * as api from '../apiClient';

let connectGen = 0;
let connectedSnapshot = false;

interface ConnectionState {
  connected: boolean;
  wsUrl: string;
  connectionError: string | null;
  profiles: string[];
  selectedProfile: string;
  connectMode: 'user' | 'isolated';
  restartDialog: { browserName: string } | null;
  restarting: boolean;
  highlightMode: string;
  connect: (mode: 'user' | 'isolated', profile?: string) => Promise<void>;
  disconnect: () => Promise<void>;
  restartConfirm: () => Promise<void>;
  restartCancel: () => void;
  createProfile: (name: string) => Promise<void>;
  handleBrowserDisconnect: () => void;
  setConnectMode: (mode: 'user' | 'isolated') => void;
  setSelectedProfile: (profile: string) => void;
  setConnectionError: (err: string | null) => void;
  setHighlightMode: (mode: string) => void;
}

function loadHighlightMode(): string {
  try { return localStorage.getItem('highlight-mode') || 'a11y'; } catch { return 'a11y'; }
}

export const useConnectionStore = _create<ConnectionState>((set, get) => ({
  connected: false,
  wsUrl: '',
  connectionError: null,
  profiles: [],
  selectedProfile: '',
  connectMode: 'user',
  restartDialog: null,
  restarting: false,
  highlightMode: loadHighlightMode(),

  connect: async (mode, profile) => {
    const localGen = ++connectGen;
    set({ connectionError: null });
    try {
      const { highlightMode } = get();
      const resp = await api.connectBrowser(mode, profile, highlightMode);
      if (localGen !== connectGen) return;
      if (resp.needsRestart) {
        set({ restartDialog: { browserName: resp.browserName || 'Chrome' } });
        return;
      }
      if (resp.success) {
        connectedSnapshot = true;
        set({ connected: true, wsUrl: resp.wsUrl || '', connectionError: null });
      } else {
        connectedSnapshot = false;
        set({ connected: false, wsUrl: '', connectionError: resp.error || null });
      }
    } catch (e) {
      if (localGen !== connectGen) return;
      console.error('Connect failed: %s', String(e));
      set({ connectionError: String(e) });
    }
  },

  disconnect: async () => {
    try { await api.disconnectBrowser(); } catch (e) { console.error('Disconnect failed: %s', String(e)); }
    connectedSnapshot = false;
    set({ connected: false, wsUrl: '', connectionError: null });
  },

  restartConfirm: async () => {
    set({ restartDialog: null, restarting: true, connectionError: null });
    try {
      const resp = await api.restartBrowser();
      if (resp.success) {
        connectedSnapshot = true;
        set({ connected: true, wsUrl: resp.wsUrl || '', connectionError: null });
      } else {
        set({ connectionError: resp.error || null });
      }
    } catch (e) {
      console.error('Restart failed: %s', String(e));
      set({ connectionError: String(e) });
    } finally {
      set({ restarting: false });
    }
  },

  restartCancel: () => {
    set({ restartDialog: null });
  },

  createProfile: async (name) => {
    if (!name.trim()) return;
    try {
      const resp = await api.createIsolatedProfile(name.trim());
      if (resp.created) {
        set((s) => {
          if (s.profiles.includes(resp.profile_name)) return s;
          return { profiles: [...s.profiles, resp.profile_name], selectedProfile: resp.profile_name };
        });
      } else {
        window.alert('Creation failed' + ': ' + (resp.error || 'Unknown error'));
      }
    } catch (e) {
      window.alert('Creation failed' + ': ' + String(e));
    }
  },

  handleBrowserDisconnect: () => {
    if (connectedSnapshot) connectGen++;
    connectedSnapshot = false;
    set({ connected: false, wsUrl: '' });
  },

  setConnectMode: (mode) => set({ connectMode: mode }),
  setSelectedProfile: (profile) => set({ selectedProfile: profile }),
  setConnectionError: (err) => set({ connectionError: err }),
  setHighlightMode: (mode) => {
    set({ highlightMode: mode });
    try { localStorage.setItem('highlight-mode', mode); } catch { /* ok */ }
  },
}));

// Load profiles on module init
api.listIsolatedProfiles().then(r => {
  if (r.profiles && r.profiles.length > 0) {
    useConnectionStore.getState().setSelectedProfile(r.profiles[0]);
    useConnectionStore.setState({ profiles: r.profiles });
  }
}).catch((e) => { console.error('listIsolatedProfiles failed: %s', String(e)); });
