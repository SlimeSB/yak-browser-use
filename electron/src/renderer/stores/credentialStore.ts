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
  refreshCredentials: () => Promise<void>;
}

export const useCredentialStore = _create<CredentialState>((set, get) => ({
  credKeys: [],
  credKey: '',
  credValue: '',
  setCredKey: (key) => set({ credKey: key }),
  setCredValue: (value) => set({ credValue: value }),
  refreshCredentials: async () => {
    const r = await api.listCredentials();
    if (r.params) set({ credKeys: r.params });
  },
  addCredential: async () => {
    const { credKey, credValue } = get();
    if (!credKey.trim() || !credValue.trim()) return;
    const r = await api.setCredential(credKey.trim(), credValue);
    if (!r.set) return;
    set({ credKey: '', credValue: '' });
    await get().refreshCredentials();
  },
  removeCredential: async (key) => {
    if (!key.trim()) return;
    await api.deleteCredential(key);
    await get().refreshCredentials();
  },
}));
