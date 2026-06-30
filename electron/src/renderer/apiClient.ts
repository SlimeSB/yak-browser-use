import type { PipelineMeta, VersionInfo, ChatMessage, PresetDefinition } from './types';

// ── Base URL resolution ──────────────────────────────────────

let _cachedBaseUrl = '';
let _baseUrlPromise: Promise<string> | null = null;

async function _resolveBaseUrl(): Promise<string> {
  if (_cachedBaseUrl) return _cachedBaseUrl;

  const electronApi = window.electronAPI;
  if (!electronApi?.getPort) return '';

  for (let attempt = 0; attempt < 60; attempt++) {
    try {
      const port = await electronApi.getPort();
      if (port > 0) {
        _cachedBaseUrl = `http://127.0.0.1:${port}`;
        return _cachedBaseUrl;
      }
    } catch { /* backend not ready */ }
    await new Promise(r => setTimeout(r, 100));
  }
  return '';
}

export function getBaseUrl(): Promise<string> {
  if (_cachedBaseUrl) return Promise.resolve(_cachedBaseUrl);
  if (!_baseUrlPromise) _baseUrlPromise = _resolveBaseUrl();
  return _baseUrlPromise;
}

// ── HTTP helpers ─────────────────────────────────────────────

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const base = await getBaseUrl();
  const resp = await fetch(`${base}${path}`, init);
  if (!resp.ok) {
    const text = await resp.text().catch(() => '');
    throw new ApiError(resp.status, text.slice(0, 200));
  }
  return resp.json();
}

export class ApiError extends Error {
  constructor(public status: number, public body: string) {
    super(`HTTP ${status}: ${body}`);
  }
}

// ── Pipeline ─────────────────────────────────────────────────

export function listPipelines() {
  return apiFetch<{ pipelines: PipelineMeta[] }>('/api/pipelines');
}

export function getPipeline(name: string) {
  return apiFetch<{ name: string; content: string; meta: PipelineMeta }>(
    `/api/pipelines/${encodeURIComponent(name)}`
  );
}

export function deletePipeline(name: string) {
  return apiFetch<{ ok: boolean; name: string; error?: string }>(
    `/api/pipelines/${encodeURIComponent(name)}`,
    { method: 'DELETE' }
  );
}

export function savePipeline(name: string, content: string) {
  return apiFetch<{ ok: boolean; name: string; error?: string }>(
    `/api/pipelines/${encodeURIComponent(name)}`,
    { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ content }) }
  );
}

export function runPipeline(agentMd: string, params?: Record<string, string>) {
  return apiFetch<{ status?: string; run_id?: string; pipeline?: string; data?: Record<string, unknown>; errors?: string[]; error?: string }>(
    '/api/run',
    { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ pipeline: agentMd, params: params || {} }) }
  );
}

export function cancelPipeline(pipelineName: string, runId: string) {
  return apiFetch<{ cancelled?: boolean; error?: string }>(
    `/api/pipeline/${encodeURIComponent(pipelineName)}/${encodeURIComponent(runId)}/cancel`,
    { method: 'POST' }
  );
}

export function reviewPipeline(threadId: string, action: string, reason?: string) {
  return apiFetch<{ status?: string; error?: string }>(
    `/api/pipeline/${encodeURIComponent(threadId)}/review`,
    { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ action, reason: reason || '' }) }
  );
}

// ── Chat ─────────────────────────────────────────────────────

export function chat(message: string, pipelineName?: string) {
  return apiFetch<{ ok?: boolean; error?: string }>(
    '/api/chat',
    { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ message, pipeline_name: pipelineName }) }
  );
}

export function chatReset() {
  return apiFetch<{ ok?: boolean; session_id?: string; status?: string }>('/api/chat/reset', { method: 'POST' });
}

export function chatCancel() {
  return apiFetch<{ ok?: boolean }>('/api/chat/cancel', { method: 'POST' });
}

export function chatConfirm(editId: string) {
  return apiFetch<{ status?: string; error?: string }>(
    '/api/chat/confirm',
    { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ edit_id: editId }) }
  );
}

export function chatRevert(editId: string) {
  return apiFetch<{ status?: string; error?: string }>(
    '/api/chat/revert',
    { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ edit_id: editId }) }
  );
}

// ── Session ──────────────────────────────────────────────────

export function newSession(pipelineName: string) {
  return apiFetch<{ session_id: string; created_at: number; pipeline_name: string }>(
    '/api/session/new',
    { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ pipeline_name: pipelineName }) }
  );
}

export function switchSession(pipelineName: string) {
  return apiFetch<{ sessions?: Session[] }>(
    '/api/session/switch',
    { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ pipeline_name: pipelineName }) }
  );
}

export function listSessions(pipelineName: string) {
  return apiFetch<{ sessions?: Session[] }>(
    `/api/session/${encodeURIComponent(pipelineName)}/list`
  );
}

export function getSessionData(pipelineName: string, sessionId: string) {
  return apiFetch<{ session?: { messages?: ChatMessage[] } & Record<string, unknown> }>(
    `/api/session/${encodeURIComponent(pipelineName)}/${encodeURIComponent(sessionId)}`
  );
}

export function archiveSession(pipelineName: string, sessionId: string) {
  return apiFetch<{ ok: boolean; error?: string }>(
    `/api/session/${encodeURIComponent(pipelineName)}/${encodeURIComponent(sessionId)}/archive`,
    { method: 'POST' }
  );
}

// ── Versions ─────────────────────────────────────────────────

export function listVersions(pipelineName: string) {
  return apiFetch<{ versions: VersionInfo[] }>(`/api/versions/${encodeURIComponent(pipelineName)}`);
}

export function getVersion(pipelineName: string, version: string) {
  return apiFetch<{ version: string; content: string }>(
    `/api/versions/${encodeURIComponent(pipelineName)}/${encodeURIComponent(version)}`
  );
}

export function relearn(pipelineName: string) {
  return apiFetch<{ deleted: boolean; version?: string }>(
    `/api/versions/${encodeURIComponent(pipelineName)}/relearn`,
    { method: 'POST' }
  );
}

// ── Chrome ───────────────────────────────────────────────────

export function listIsolatedProfiles() {
  return apiFetch<{ profiles: string[] }>('/api/chrome/isolated-profiles');
}

export function createIsolatedProfile(name: string) {
  return apiFetch<{ created: boolean; profile_name: string; error?: string }>(
    `/api/chrome/isolated-profiles/${encodeURIComponent(name)}`,
    { method: 'POST' }
  );
}

export function connectBrowser(mode: string, profileName?: string, highlightMode?: string) {
  return apiFetch<{ success: boolean; wsUrl?: string; error?: string | null; needsRestart?: boolean; browserName?: string }>(
    '/api/chrome/connect',
    { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ mode, profile_name: profileName, highlight_mode: highlightMode || 'a11y' }) }
  );
}

export function restartBrowser() {
  return apiFetch<{ success: boolean; wsUrl?: string; error?: string | null }>('/api/chrome/restart', { method: 'POST' });
}

export function disconnectBrowser() {
  return apiFetch<{ success: boolean }>('/api/chrome/disconnect', { method: 'POST' });
}

// ── Credentials ──────────────────────────────────────────────

export function listCredentials() {
  return apiFetch<{ params: string[]; error?: string }>('/api/params');
}

export function setCredential(key: string, value: string) {
  return apiFetch<{ key: string; set: boolean; error?: string }>(
    '/api/params',
    { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ key, value }) }
  );
}

export function deleteCredential(key: string) {
  return apiFetch<{ key: string; deleted: boolean; error?: string }>(
    `/api/params/${encodeURIComponent(key)}`,
    { method: 'DELETE' }
  );
}

// ── Provider ─────────────────────────────────────────────────

export function getProviderConfig() {
  return apiFetch<{ ok: boolean; config: Record<string, unknown> }>('/api/provider-config');
}

export function setProviderConfig(config: Record<string, unknown>) {
  return apiFetch<{ ok: boolean }>('/api/provider-config', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(config),
  });
}

export function testProvider(config: Record<string, string>) {
  return apiFetch<{ ok: boolean; response?: string; error?: string }>('/api/provider-test', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(config),
  });
}

export function getProviderPresets() {
  return apiFetch<{ ok: boolean; presets?: PresetDefinition[]; error?: string }>('/api/provider-presets');
}

// ── WebSocket ────────────────────────────────────────────────

export async function createWebSocket(path: string): Promise<WebSocket> {
  const base = await getBaseUrl();
  return new WebSocket(`ws://${base.replace('http://', '')}${path}`);
}

// ── Types ────────────────────────────────────────────────────

export interface Session {
  session_id: string;
  display_name?: string | null;
  created_at: string;
  message_count: number;
  status: string;
}
