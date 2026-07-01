import { _create } from './_factory';
import * as api from '../apiClient';
import { showAlert } from '../utils/dialog';
import { readStorage, writeStorage } from '../utils/storage';

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
  // internal
  _connectGen: number;
  // actions
  connect: (mode: 'user' | 'isolated', profile?: string) => Promise<void>;
  disconnect: () => Promise<void>;
  restartConfirm: () => Promise<void>;
  restartCancel: () => void;
  createProfile: (name: string) => Promise<void>;
  handleBrowserDisconnect: () => void;
  _bumpGen: () => void;
  setConnectMode: (mode: 'user' | 'isolated') => void;
  setSelectedProfile: (profile: string) => void;
  setConnectionError: (err: string | null) => void;
  setHighlightMode: (mode: string) => void;
}

function loadHighlightMode(): string {
  return readStorage<string>('highlight-mode', 'a11y');
}

export const useConnectionStore = _create<ConnectionState>((set, get) => ({
  connected: false,
  wsUrl: '',
  connectionError: null,
  profiles: [],
  selectedProfile: '',
  connectMode: 'isolated',
  restartDialog: null,
  restarting: false,
  highlightMode: loadHighlightMode(),
  _connectGen: 0,

  connect: async (mode, profile?) => {
    const localGen = ++get()._connectGen;
    set({ connectionError: null });
    try {
      const { highlightMode, profiles } = get();
      const effectiveProfile = profile || (profiles.length > 0 ? profiles[0] : undefined);
      const resp = await api.connectBrowser(mode, effectiveProfile, highlightMode);
      if (localGen !== get()._connectGen) return; // stale
      if (resp.needsRestart) {
        set({ restartDialog: { browserName: resp.browserName || 'Chrome' } });
        return;
      }
      if (resp.success) {
        set({ connected: true, wsUrl: resp.wsUrl || '', connectionError: null });
      } else {
        set({ connected: false, wsUrl: '', connectionError: resp.error || null });
      }
    } catch (e) {
      if (localGen !== get()._connectGen) return;
      console.error('Connect failed: %s', String(e));
      set({ connectionError: String(e) });
    }
  },

  disconnect: async () => {
    try { await api.disconnectBrowser(); } catch { /* ok */ }
    set({ connected: false, wsUrl: '', connectionError: null });
  },

  restartConfirm: async () => {
    set({ restartDialog: null, restarting: true, connectionError: null });
    try {
      const resp = await api.restartBrowser();
      if (resp.success) {
        set({ connected: true, wsUrl: resp.wsUrl || '', connectionError: null });
      } else {
        set({ connectionError: resp.error || null });
      }
    } catch (e) {
      set({ connectionError: String(e) });
    } finally {
      set({ restarting: false });
    }
  },

  restartCancel: () => set({ restartDialog: null }),

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
        showAlert('Creation failed: ' + (resp.error || 'Unknown'));
      }
    } catch (e) {
      showAlert('Creation failed: ' + String(e));
    }
  },

  handleBrowserDisconnect: () => {
    get()._bumpGen();
    set({ connected: false, wsUrl: '' });
  },

  _bumpGen: () => set((s) => ({ _connectGen: s._connectGen + 1 })),

  setConnectMode: (mode) => set({ connectMode: mode }),
  setSelectedProfile: (profile) => set({ selectedProfile: profile }),
  setConnectionError: (err) => set({ connectionError: err }),
  setHighlightMode: (mode) => {
    set({ highlightMode: mode });
    writeStorage('highlight-mode', mode);
  },
}));

// Load profiles on module init
api.listIsolatedProfiles().then(r => {
  if (r.profiles && r.profiles.length > 0) {
    useConnectionStore.setState({ profiles: r.profiles, selectedProfile: r.profiles[0] });
  }
}).catch((e) => { console.error('listIsolatedProfiles failed: %s', String(e)); });
