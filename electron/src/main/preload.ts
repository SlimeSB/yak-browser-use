import { contextBridge, ipcRenderer } from 'electron';

contextBridge.exposeInMainWorld('electronAPI', {
  // Window controls
  windowMinimize: () => ipcRenderer.invoke('window:minimize'),
  windowMaximize: () => ipcRenderer.invoke('window:maximize'),
  windowClose: () => ipcRenderer.invoke('window:close'),

  // API
  run: (agentMd: string, params?: Record<string, string>) => ipcRenderer.invoke('api:run', { agentMd, params }),
  convert: (document: string) => ipcRenderer.invoke('api:convert', document),
  chatEdit: (agentMd: string, instruction: string, history?: Record<string, string>[]) => ipcRenderer.invoke('api:chatEdit', { agentMd, instruction, history }),
  status: () => ipcRenderer.invoke('api:status'),
  chromeStatus: () => ipcRenderer.invoke('api:chrome-status'),
  connectBrowser: (mode: string, profileName?: string) => ipcRenderer.invoke('browser:connect', { mode, profileName }),
  restartBrowser: () => ipcRenderer.invoke('browser:restart'),
  disconnectBrowser: () => ipcRenderer.invoke('browser:disconnect'),
  listIsolatedProfiles: () => ipcRenderer.invoke('browser:isolated-profiles-list'),
  createIsolatedProfile: (name: string) => ipcRenderer.invoke('browser:isolated-profiles-create', name),
  exportExcel: (data: unknown) => ipcRenderer.invoke('export:excel', { data }),
  exportCsv: (data: unknown) => ipcRenderer.invoke('export:csv', { data }),
  // Version management
  listVersions: (pipelineName: string) => ipcRenderer.invoke('versions:list', pipelineName),
  getVersion: (pipelineName: string, version: string) => ipcRenderer.invoke('versions:get', { pipelineName, version }),
  relearn: (pipelineName: string) => ipcRenderer.invoke('versions:relearn', pipelineName),

  // Pipeline control
  cancelPipeline: (pipelineName: string, runId: string) => ipcRenderer.invoke('pipeline:cancel', { pipelineName, runId }),
  reviewPipeline: (threadId: string, action: string, reason?: string) => ipcRenderer.invoke('pipeline:review', { threadId, action, reason }),

  // Credentials
  listCredentials: () => ipcRenderer.invoke('credentials:list'),
  setCredential: (key: string, value: string) => ipcRenderer.invoke('credentials:set', { key, value }),
  deleteCredential: (key: string) => ipcRenderer.invoke('credentials:delete', key),

  // Backend port for WebSocket
  getPort: () => ipcRenderer.invoke('get:port'),

  // Pipeline discovery
  listPipelines: () => ipcRenderer.invoke('pipelines:list'),
  getPipeline: (name: string) => ipcRenderer.invoke('pipelines:get', name),

  // Dialogs
  showAlert: (message: string) => ipcRenderer.invoke('dialog:alert', message),
});
