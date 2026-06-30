import { _create } from './_factory';
import * as api from '../apiClient';

interface CredentialState {
  credKeys: string[];
  credKey: string;
  credValue: string;
  setCredKey: (key: string) => void;
  setCredValue: (value: string) => void;
  addCredential: () => Promise<void>;
  removeCredential: (key: string) => Promise<void>;
}

export const useCredentialStore = _create<CredentialState>((set, get) => ({
  credKeys: [],
  credKey: '',
  credValue: '',
  setCredKey: (key) => set({ credKey: key }),
  setCredValue: (value) => set({ credValue: value }),
  addCredential: async () => {
    const { credKey, credValue } = get();
    if (!credKey.trim() || !credValue.trim()) return;
    await api.setCredential(credKey.trim(), credValue);
    set({ credKey: '', credValue: '' });
    const r = await api.listCredentials();
    if (r.params) set({ credKeys: r.params });
  },
  removeCredential: async (key) => {
    await api.deleteCredential(key);
    set((s) => ({ credKeys: s.credKeys.filter(k => k !== key) }));
  },
}));
