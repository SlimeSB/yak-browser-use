import type { PipelineMeta, VersionInfo, ChatMessage, PresetDefinition } from './types';

async function getBaseUrl(): Promise<string> {
  if ((window as any).electronAPI?.getPort) {
    const port = await (window as any).electronAPI.getPort();
    return `http://127.0.0.1:${port}`;
  }
  return '';
}

async function apiFetch(path: string, init?: RequestInit): Promise<any> {
  const base = await getBaseUrl();
  const resp = await fetch(`${base}${path}`, init);
  if (!resp.ok) {
    const text = await resp.text().catch(() => '');
    throw new Error(`HTTP ${resp.status}: ${text.slice(0, 200)}`);
  }
  return resp.json();
}

async function safeFetch(path: string, init?: RequestInit): Promise<{ ok: boolean; data?: any; error?: string }> {
  try {
    const base = await getBaseUrl();
    const resp = await fetch(`${base}${path}`, init);
    if (!resp.ok) {
      const text = await resp.text().catch(() => '');
      return { ok: false, error: `HTTP ${resp.status}: ${text.slice(0, 200)}` };
    }
    return { ok: true, data: await resp.json() };
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

export async function createWebSocket(path: string): Promise<WebSocket> {
  if ((window as any).electronAPI?.getPort) {
    const port = await (window as any).electronAPI.getPort();
    return new WebSocket(`ws://127.0.0.1:${port}${path}`);
  }
  return new WebSocket(`ws://${window.location.host}${path}`);
}

export async function listPipelines(): Promise<{ pipelines: PipelineMeta[]; error?: string }> {
  return apiFetch('/api/pipelines');
}

export async function getPipeline(name: string): Promise<{ name: string; content: string; meta: PipelineMeta; error?: string }> {
  return apiFetch(`/api/pipelines/${encodeURIComponent(name)}`);
}

export async function deletePipeline(name: string): Promise<{ ok: boolean; name: string; error?: string }> {
  return apiFetch(`/api/pipelines/${encodeURIComponent(name)}`, { method: 'DELETE' });
}

export async function savePipeline(name: string, content: string): Promise<{ ok: boolean; name: string; error?: string }> {
  return apiFetch(`/api/pipelines/${encodeURIComponent(name)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content }),
  });
}

export async function listIsolatedProfiles(): Promise<{ profiles: string[] }> {
  const result = await safeFetch('/api/chrome/isolated-profiles');
  if (!result.ok) return { profiles: ['Default Temp'] };
  return { profiles: result.data?.profiles || [] };
}

export async function createIsolatedProfile(name: string): Promise<{ created: boolean; profile_name: string; error?: string }> {
  const result = await safeFetch(`/api/chrome/isolated-profiles/${encodeURIComponent(name)}`, { method: 'POST' });
  return {
    created: result.ok && !!result.data?.created,
    profile_name: result.data?.profile_name || name,
    error: result.error || undefined,
  };
}

export async function connectBrowser(mode: string, profileName?: string, highlightMode?: string): Promise<{ success: boolean; wsUrl?: string; error?: string | null; needsRestart?: boolean; browserName?: string }> {
  const result = await safeFetch('/api/chrome/connect', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ mode, profile_name: profileName, highlight_mode: highlightMode || 'a11y' }),
  });
  if (!result.ok) throw new Error(result.error);
  const data = result.data || {};
  return {
    success: data.connected ?? false,
    wsUrl: data.ws_url ?? '',
    error: data.error ?? null,
    needsRestart: data.needs_restart ?? false,
    browserName: data.browser_name ?? '',
  };
}

export async function restartBrowser(): Promise<{ success: boolean; wsUrl?: string; error?: string | null }> {
  const result = await safeFetch('/api/chrome/restart', { method: 'POST' });
  if (!result.ok) throw new Error(result.error);
  const data = result.data || {};
  return {
    success: data.connected ?? false,
    wsUrl: data.ws_url ?? '',
    error: data.error ?? null,
  };
}

export async function disconnectBrowser(): Promise<{ success: boolean }> {
  const result = await safeFetch('/api/chrome/disconnect', { method: 'POST' });
  if (!result.ok) return { success: false };
  return { success: result.data?.disconnected ?? true };
}

export async function run(agentMd: string, params?: Record<string, string>): Promise<{ status?: string; run_id?: string; pipeline?: string; data?: Record<string, unknown>; errors?: string[]; error?: string }> {
  return apiFetch('/api/run', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pipeline: agentMd, params: params || {} }),
  });
}

export async function chat(message: string, pipelineName?: string): Promise<{ ok?: boolean; response?: string; status?: string; turn_count?: number; duration_ms?: number; error?: string }> {
  return apiFetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, pipeline_name: pipelineName }),
  });
}

export async function chatReset(): Promise<{ ok?: boolean; session_id?: string; status?: string }> {
  return apiFetch('/api/chat/reset', { method: 'POST' });
}

export async function chatCancel(): Promise<{ ok?: boolean }> {
  return apiFetch('/api/chat/cancel', { method: 'POST' });
}

export async function newSession(pipelineName: string): Promise<{ session_id: string; created_at: number; pipeline_name: string }> {
  return apiFetch('/api/session/new', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pipeline_name: pipelineName }),
  });
}

export async function switchSession(pipelineName: string): Promise<{ sessions?: Array<{ session_id: string; display_name?: string | null; created_at: string; message_count: number; status: string }> }> {
  return apiFetch('/api/session/switch', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pipeline_name: pipelineName }),
  });
}

export async function listSessions(pipelineName: string): Promise<{ sessions?: Array<{ session_id: string; display_name?: string | null; created_at: string; message_count: number; status: string }> }> {
  return apiFetch(`/api/session/${encodeURIComponent(pipelineName)}/list`);
}

export async function getSessionData(pipelineName: string, sessionId: string): Promise<{ session?: { messages?: ChatMessage[] } & Record<string, unknown> }> {
  return apiFetch(`/api/session/${encodeURIComponent(pipelineName)}/${encodeURIComponent(sessionId)}`);
}

export async function archiveSession(pipelineName: string, sessionId: string): Promise<{ ok: boolean; error?: string }> {
  return apiFetch(`/api/session/${encodeURIComponent(pipelineName)}/${encodeURIComponent(sessionId)}/archive`, { method: 'POST' });
}

export async function listVersions(pipelineName: string): Promise<{ versions: VersionInfo[] }> {
  return apiFetch(`/api/versions/${encodeURIComponent(pipelineName)}`);
}

export async function getVersion(pipelineName: string, version: string): Promise<{ version: string; content: string }> {
  return apiFetch(`/api/versions/${encodeURIComponent(pipelineName)}/${encodeURIComponent(version)}`);
}

export async function relearn(pipelineName: string): Promise<{ deleted: boolean; version?: string }> {
  return apiFetch(`/api/versions/${encodeURIComponent(pipelineName)}/relearn`, { method: 'POST' });
}

export async function cancelPipeline(pipelineName: string, runId: string): Promise<{ cancelled?: boolean; error?: string }> {
  return apiFetch(`/api/pipeline/${encodeURIComponent(pipelineName)}/${encodeURIComponent(runId)}/cancel`, { method: 'POST' });
}

export async function reviewPipeline(threadId: string, action: string, reason?: string): Promise<{ status?: string; error?: string }> {
  return apiFetch(`/api/pipeline/${encodeURIComponent(threadId)}/review`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action, reason: reason || '' }),
  });
}

export async function listCredentials(): Promise<{ params: string[]; error?: string }> {
  return apiFetch('/api/params');
}

export async function setCredential(key: string, value: string): Promise<{ key: string; set: boolean; error?: string }> {
  return apiFetch('/api/params', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ key, value }),
  });
}

export async function deleteCredential(key: string): Promise<{ key: string; deleted: boolean; error?: string }> {
  return apiFetch(`/api/params/${encodeURIComponent(key)}`, { method: 'DELETE' });
}

export async function chatConfirm(editId: string): Promise<{ status?: string; error?: string }> {
  const result = await safeFetch('/api/chat/confirm', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ edit_id: editId }),
  });
  if (!result.ok) {
    return { status: 'error', error: result.error };
  }
  return result.data as { status?: string; error?: string };
}

export async function chatRevert(editId: string): Promise<{ status?: string; error?: string }> {
  const result = await safeFetch('/api/chat/revert', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ edit_id: editId }),
  });
  if (!result.ok) {
    return { status: 'error', error: result.error };
  }
  return result.data as { status?: string; error?: string };
}

export async function getProviderConfig(): Promise<{ ok: boolean; config: Record<string, unknown> }> {
  return apiFetch('/api/provider-config');
}

export async function setProviderConfig(config: Record<string, unknown>): Promise<{ ok: boolean }> {
  return apiFetch('/api/provider-config', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config),
  });
}

export async function testProvider(config: Record<string, string>): Promise<{ ok: boolean; response?: string; error?: string }> {
  return apiFetch('/api/provider-test', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config),
  });
}

export async function getProviderPresets(): Promise<{ ok: boolean; presets?: PresetDefinition[]; error?: string }> {
  return apiFetch('/api/provider-presets');
}
