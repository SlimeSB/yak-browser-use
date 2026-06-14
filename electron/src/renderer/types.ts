export interface EventData {
  type: string;
  timestamp: string;
  node_name: string;
  data: Record<string, unknown>;
}

export interface PipelineMeta {
  name: string;
  title: string;
  description: string;
  inputs: Record<string, string>;
  stages: string[];
  step_count: number;
  defaults?: Record<string, string>;
}

export interface VersionInfo {
  version: string;
  filename: string;
  size: number;
  created_at: string;
}

export interface PresetModel {
  id: string;
  name: string;
  context: number | null;
}

export interface PresetDefinition {
  id: string;
  name: string;
  api_base: string;
  env: string[];
  models: PresetModel[];
}

export interface ChatMessage {
  role: 'user' | 'assistant' | 'tool' | 'system';
  content: string;
  reasoning?: string;
  toolName?: string;
  toolOk?: boolean;
  toolDuration?: number;
}

export interface ChatAgentEvent {
  event: string;
  data: Record<string, unknown>;
}

export interface Param {
  key: string;
  value: string;
}

export interface PendingEdit {
  edit_id: string;
  original: string;
  modified: string;
  explanation: string;
}

declare global {
  interface Window {
    electronAPI: {
      run: (agentMd: string, params?: Record<string, string>) => Promise<{ status?: string; run_id?: string; pipeline?: string; data?: Record<string, unknown>; errors?: string[]; error?: string }>;
      convert: (document: string) => Promise<{ agent_md?: string; error?: string }>;
      status: () => Promise<{ current_step?: string; step_index?: number; status?: string }>;
      chromeStatus: () => Promise<{ connected?: boolean; ws_url?: string }>;
      connectBrowser: (mode: string, profileName?: string) => Promise<{ success: boolean; wsUrl?: string; error?: string | null; needsRestart?: boolean; browserName?: string }>;
      restartBrowser: () => Promise<{ success: boolean; wsUrl?: string; error?: string | null }>;
      disconnectBrowser: () => Promise<{ success: boolean }>;
      listIsolatedProfiles: () => Promise<{ profiles: string[] }>;
      createIsolatedProfile: (name: string) => Promise<{ created: boolean; profile_name: string; error?: string }>;
      openCsvDialog: () => Promise<{ success: boolean; content?: string; filePath?: string; error?: string }>;
      exportExcel: (data: unknown) => Promise<{ success: boolean; filePath?: string; error?: string }>;
      exportCsv: (data: unknown) => Promise<{ success: boolean; filePath?: string; rows?: number; error?: string }>;
      listPipelines: () => Promise<{ pipelines: PipelineMeta[]; error?: string }>;
      getPipeline: (name: string) => Promise<{ name: string; agent_md: string; meta: PipelineMeta; error?: string }>;
      chat: (message: string) => Promise<{ ok?: boolean; response?: string; status?: string; turn_count?: number; duration_ms?: number; error?: string }>;
      chatReset: () => Promise<{ ok?: boolean; session_id?: string; status?: string }>;
      chatCancel: () => Promise<{ ok?: boolean }>;
      getSession: () => Promise<{ session?: { session_id: string; pipeline_name: string; status: string; message_count: number } | null }>;
      listPresets: () => Promise<{ presets: Array<{ name: string; path: string; modified: number }> }>;
      savePreset: (name: string, content: string) => Promise<{ ok?: boolean; path?: string }>;
      compilePreset: (name: string) => Promise<{ ok?: boolean; path?: string; content?: string }>;
      listVersions: (pipelineName: string) => Promise<{ versions: VersionInfo[] }>;
      getVersion: (pipelineName: string, version: string) => Promise<{ version: string; content: string }>;
      relearn: (pipelineName: string) => Promise<{ deleted: boolean; version?: string }>;
      windowMinimize: () => Promise<void>;
      windowMaximize: () => Promise<void>;
      windowClose: () => Promise<void>;
      cancelPipeline: (pipelineName: string, runId: string) => Promise<{ cancelled?: boolean; error?: string }>;
      listCredentials: () => Promise<{ params: string[]; error?: string }>;
      setCredential: (key: string, value: string) => Promise<{ key: string; set: boolean; error?: string }>;
      deleteCredential: (key: string) => Promise<{ key: string; deleted: boolean; error?: string }>;
      chatConfirm: (editId: string) => Promise<{ status?: string; error?: string }>;
      chatRevert: (editId: string) => Promise<{ status?: string; error?: string }>;
      reviewPipeline: (threadId: string, action: string, reason?: string) => Promise<{ status?: string; error?: string }>;
      getPort: () => Promise<number>;
      showAlert: (message: string) => Promise<void>;
      getProviderConfig: () => Promise<{ ok: boolean; config: Record<string, unknown> }>;
      setProviderConfig: (config: Record<string, unknown>) => Promise<{ ok: boolean }>;
      testProvider: (config: Record<string, string>) => Promise<{ ok: boolean; response?: string; error?: string }>;
      getProviderPresets: () => Promise<{ ok: boolean; presets?: PresetDefinition[]; error?: string }>;
    };
  }
}
