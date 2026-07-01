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

let _msgId = 0;
export function nextMsgId(): string { return `msg_${++_msgId}`; }

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'tool' | 'system';
  content: string;
  reasoning?: string;
  toolName?: string;
  toolCallId?: string;
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

export interface SessionMeta {
  session_id: string;
  display_name?: string | null;
  created_at: string;
  message_count: number;
  status: string;
}

export interface TreeNode {
  name: string;
  label: string;
  sessions: SessionMeta[];
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
      connectBrowser: (mode: string, profileName?: string, highlightMode?: string) => Promise<{ success: boolean; wsUrl?: string; error?: string | null; needsRestart?: boolean; browserName?: string }>;
      restartBrowser: () => Promise<{ success: boolean; wsUrl?: string; error?: string | null }>;
      disconnectBrowser: () => Promise<{ success: boolean }>;
      listIsolatedProfiles: () => Promise<{ profiles: string[] }>;
      createIsolatedProfile: (name: string) => Promise<{ created: boolean; profile_name: string; error?: string }>;
      listPipelines: () => Promise<{ pipelines: PipelineMeta[]; error?: string }>;
      getPipeline: (name: string) => Promise<{ name: string; content: string; meta: PipelineMeta; error?: string }>;
      deletePipeline: (name: string) => Promise<{ ok: boolean; name: string; error?: string }>;
      chat: (message: string, pipelineName?: string) => Promise<{ ok?: boolean; response?: string; status?: string; turn_count?: number; duration_ms?: number; error?: string }>;
      chatReset: () => Promise<{ ok?: boolean; session_id?: string; status?: string }>;
      chatCancel: () => Promise<{ ok?: boolean }>;
      newSession: (pipelineName: string) => Promise<{ session_id: string; created_at: number; pipeline_name: string }>;
      switchSession: (pipelineName: string) => Promise<{ sessions?: Array<{ session_id: string; display_name?: string | null; created_at: string; message_count: number; status: string }> }>;
      listSessions: (pipelineName: string) => Promise<{ sessions?: Array<{ session_id: string; display_name?: string | null; created_at: string; message_count: number; status: string }> }>;
      getSessionData: (pipelineName: string, sessionId: string) => Promise<{ session?: { messages?: ChatMessage[] } & Record<string, unknown> }>;
      archiveSession: (pipelineName: string, sessionId: string) => Promise<{ ok: boolean; error?: string }>;
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
