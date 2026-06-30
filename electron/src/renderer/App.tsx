import React, { useState, useCallback, useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import './styles/global.css';
import type { PipelineMeta, EventData, ChatMessage, PendingEdit, SessionMeta, TreeNode } from './types';
import * as api from './apiClient';
import TitleBar from './components/TitleBar';
import ConnectionBar from './components/ConnectionBar';
import StatusBar from './components/StatusBar';
import ExecTab from './components/tabs/ExecTab';
import ChatTab from './components/tabs/ChatTab';
import LogTab from './components/tabs/LogTab';
import PipelinesTab from './components/tabs/PipelinesTab';
import ParamsTab from './components/tabs/ParamsTab';
import SettingsTab from './components/tabs/SettingsTab';

function interpolateTemplate(template: string, ctx: Record<string, string>): string {
  return template.replace(/{{([\w.]+)}}/g, (_match, key: string) => ctx[key] ?? `{{${key}}}`);
}

export default function App() {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState('exec');
  const [pipelines, setPipelines] = useState<PipelineMeta[]>([]);
  const [events, setEvents] = useState<EventData[]>([]);
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [resultErrors, setResultErrors] = useState<string[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [activePreset, setActivePreset] = useState('');
  const [pipelineCache, setPipelineCache] = useState<Record<string, string>>({});
  const [connected, setConnected] = useState(false);
  const [wsUrl, setWsUrl] = useState('');
  const [connectionError, setConnectionError] = useState<string | null>(null);
  const connectGenRef = useRef(0);
  const connectDebounceRef = useRef<ReturnType<typeof setTimeout>>();
  const disconnectedRef = useRef(false);

  const [connectMode, setConnectMode] = useState<'user' | 'isolated'>('user');
  const [selectedProfile, setSelectedProfile] = useState(t('common.defaultTemp'));
  const [profiles, setProfiles] = useState<string[]>([t('common.defaultTemp')]);
  const [params, setParams] = useState<Record<string, string>>({});
  const [restartDialog, setRestartDialog] = useState<{ browserName: string } | null>(null);
  const [restarting, setRestarting] = useState(false);
  const [reviewMode, setReviewMode] = useState('none');
  const [highlightMode, setHighlightMode] = useState(() => {
    try { return localStorage.getItem('highlight-mode') || 'a11y'; } catch { return 'a11y'; }
  });
  const [currentRunId, setCurrentRunId] = useState('');
  const [currentPipeline, setCurrentPipeline] = useState('');
  const [cancelling, setCancelling] = useState(false);
  const [credKeys, setCredKeys] = useState<string[]>([]);
  const [credKey, setCredKey] = useState('');
  const [credValue, setCredValue] = useState('');

  const [theme, setTheme] = useState<'dark' | 'light'>(() => {
    try { return (localStorage.getItem('theme') as 'dark' | 'light') || 'dark'; } catch { return 'dark'; }
  });

  const setThemePersist = useCallback((t: 'dark' | 'light') => {
    setTheme(t);
    document.documentElement.setAttribute('data-theme', t);
    try { localStorage.setItem('theme', t); } catch { /* ok */ }
  }, []);

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
  }, [theme]);

  const [chatLayoutReversed, setChatLayoutReversed] = useState(() => {
    try { return localStorage.getItem('chat-layout-reversed') === 'true'; } catch { return false; }
  });

  const [pendingReview, setPendingReview] = useState<{
    extraOps: Array<{ type: string; value?: string; selector?: string }>;
    reason: string;
    guardLayer: string;
    threadId: string;
  } | null>(null);

  const [pendingEdits, setPendingEdits] = useState<PendingEdit[]>([]);
  const processedEditIdsRef = useRef<Set<string>>(new Set());
  const streamStatesRef = useRef<Record<number, { accumulating: string; reasoningParts: string[]; complete: boolean }>>({});

  const activePendingEdit = pendingEdits.length > 0 ? pendingEdits[0] : null;

  const [pipelineEditor, setPipelineEditor] = useState('');
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [currentSessionId, setCurrentSessionId] = useState<string>('');
  const [loadingSession, setLoadingSession] = useState(false);
  const [chatSessions, setChatSessions] = useState<SessionMeta[]>([]);
  const [pipelineSessions, setPipelineSessions] = useState<Record<string, SessionMeta[]>>({});
  const [expandedNodes, setExpandedNodes] = useState<Set<string>>(new Set(['__chat__']));
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => {
    try { return localStorage.getItem('chat-sidebar-collapsed') === 'true'; } catch { return false; }
  });



  const loadSessions = useCallback(async (pipelineName: string) => {
    try {
      const r = await api.listSessions(pipelineName);
      const list = r.sessions || [];
      if (pipelineName === '__chat__' || !pipelineName) {
        setChatSessions(list);
      } else {
        setPipelineSessions(prev => ({ ...prev, [pipelineName]: list }));
      }
      return list;
    } catch (e) {
      console.error('listSessions failed: %s', String(e));
      if (pipelineName === '__chat__' || !pipelineName) {
        setChatSessions([]);
      } else {
        setPipelineSessions(prev => ({ ...prev, [pipelineName]: [] }));
      }
      return [];
    }
  }, []);

  const switchPipeline = useCallback(async (pipelineName: string) => {
    setActivePreset(pipelineName);
    setChatMessages([]);
    setCurrentSessionId('');
    try {
      const r = await api.switchSession(pipelineName);
      const list = r.sessions || [];
      if (pipelineName === '__chat__' || !pipelineName) {
        setChatSessions(list);
      } else {
        setPipelineSessions(prev => ({ ...prev, [pipelineName]: list }));
      }
      if (list.length > 0) {
        setCurrentSessionId(list[0].session_id);
      }
    } catch (e) {
      console.error('switchSession failed: %s', String(e));
      if (pipelineName === '__chat__' || !pipelineName) {
        setChatSessions([]);
      } else {
        setPipelineSessions(prev => ({ ...prev, [pipelineName]: [] }));
      }
    }
  }, []);

  const handleToggleExpand = useCallback(async (name: string) => {
    // Switch to this pipeline if not active
    if (name !== activePreset) {
      await switchPipeline(name);
    }
    // Toggle expand
    setExpandedNodes(prev => {
      const next = new Set(prev);
      if (next.has(name)) {
        next.delete(name);
      } else {
        next.add(name);
      }
      return next;
    });
    // Load sessions on first expand
    if (name !== '__chat__' && !pipelineSessions[name]) {
      await loadSessions(name);
    }
  }, [activePreset, switchPipeline, pipelineSessions, loadSessions]);

  const toggleSidebar = useCallback(() => {
    setSidebarCollapsed(prev => {
      const next = !prev;
      try { localStorage.setItem('chat-sidebar-collapsed', String(next)); } catch { /* ok */ }
      return next;
    });
  }, []);

  useEffect(() => {
    let cancelled = false;
    api.listPipelines().then(async r => {
      if (cancelled) return;
      // Always load __chat__ sessions first
      const chatList = await loadSessions('__chat__');
      if (cancelled) return;
      if (r.pipelines && r.pipelines.length > 0) {
        setPipelines(r.pipelines);
        const initial = r.pipelines[0].name;
        const list = await loadSessions(initial);
        if (cancelled) return;
        if (list.length > 0) setCurrentSessionId(list[0].session_id);
        setActivePreset(initial);
      } else {
        if (chatList.length > 0) setCurrentSessionId(chatList[0].session_id);
        setActivePreset('__chat__');
      }
    }).catch((e) => { console.error('listPipelines failed: %s', String(e)); });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    api.listIsolatedProfiles().then(r => {
      if (r.profiles && r.profiles.length > 0) {
        setProfiles(r.profiles);
      }
    }).catch((e) => { console.error('listIsolatedProfiles failed: %s', String(e)); });
  }, []);

  useEffect(() => {
    setPendingEdits([]);
  }, [activePreset]);

  // Sync sessions when activePreset changes (e.g. from exec tab)
  useEffect(() => {
    if (!activePreset || activePreset === '__chat__') return;
    if (!pipelineSessions[activePreset]) {
      loadSessions(activePreset).then(list => {
        if (list.length > 0) setCurrentSessionId(list[0].session_id);
      });
    }
  }, [activePreset]);

  useEffect(() => {
    if (!activePreset || activePreset === '__chat__') {
      setPipelineEditor('');
      return;
    }
    const preset = pipelines.find(p => p.name === activePreset);
    if (preset) {
      const cached = pipelineCache[activePreset];
      if (cached) {
        setPipelineEditor(cached);
      } else {
        api.getPipeline(activePreset).then(resp => {
          if (resp.content) {
            setPipelineCache(prev => ({ ...prev, [activePreset]: resp.content }));
            setPipelineEditor(resp.content);
          }
        }).catch((e) => { console.error('getPipeline failed: %s', String(e)); });
      }
    }
  }, [activePreset, pipelines]);

  useEffect(() => {
    const preset = pipelines.find(p => p.name === activePreset);
    if (preset) {
      const init: Record<string, string> = {};
      for (const key of Object.keys(preset.inputs ?? {})) {
        init[key] = preset.defaults?.[key] ?? '';
      }
      setParams(init);
    }
    setResult(null);
    setResultErrors(null);
    setEvents([]);
  }, [activePreset, pipelines]);

  // No auto-polling. User clicks "Connect" to trigger the check.

  useEffect(() => {
    let ws: WebSocket | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout>;
    let stopped = false;
    const connect = async () => {
      if (stopped) return;
      try {
        const newWs = await api.createWebSocket('/ws/events');
        if (stopped) { newWs.close(); return; }
        ws = newWs;
        disconnectedRef.current = false;
        ws.onmessage = (ev) => {
          try {
            const event = JSON.parse(ev.data);
            const et = event.type;

            // Chat events
            if (et === 'chat.tool_start') {
              setChatMessages(prev => [...prev, {
                role: 'tool',
                content: '',
                toolName: event.tool_name || '',
                toolCallId: event.id || '',
                toolOk: undefined,
              }]);
              setEvents(prev => [...prev, { type: et, timestamp: event.timestamp || (event._ts != null ? new Date(event._ts * 1000).toISOString() : new Date().toISOString()), node_name: event.step || event.pipeline || '', data: event }]);
            } else if (et === 'chat.tool_end') {
              const toolCallId: string = event.id || '';
              setChatMessages(prev => {
                const next = [...prev];
                for (let i = next.length - 1; i >= 0; i--) {
                  if (next[i].role === 'tool' && next[i].toolCallId === toolCallId) {
                    next[i] = {
                      ...next[i],
                      toolOk: event.ok,
                      toolDuration: event.duration_ms,
                      content: event.error || (event.ok ? 'Done' : 'Failed'),
                    };
                    break;
                  }
                }
                return next;
              });
              setEvents(prev => [...prev, { type: et, timestamp: event.timestamp || (event._ts != null ? new Date(event._ts * 1000).toISOString() : new Date().toISOString()), node_name: event.step || event.pipeline || '', data: event }]);
            } else if (et === 'chat.error') {
              setChatMessages(prev => [...prev, { role: 'assistant', content: `[Error] ${event.message || ''}` }]);
            } else if (et === 'chat.stream_start') {
              const ti = event.turn_index as number;
              streamStatesRef.current[ti] = { accumulating: '', reasoningParts: [], complete: false };
              setChatMessages(prev => {
                const next = [...prev];
                if (ti >= next.length) {
                  next.push({ role: 'assistant', content: '' });
                }
                return next;
              });
            } else if (et === 'chat.text_chunk') {
              const ti = event.turn_index as number;
              const content = event.content as string || '';
              const st = streamStatesRef.current[ti] || { accumulating: '', reasoningParts: [], complete: false };
              streamStatesRef.current[ti] = st;
              st.accumulating += content;
              setChatMessages(prev => {
                const next = [...prev];
                if (ti < next.length && next[ti].role === 'assistant') {
                  next[ti] = { ...next[ti], content: st.accumulating };
                }
                return next;
              });
            } else if (et === 'chat.think_chunk') {
              const ti = event.turn_index as number;
              const content = event.content as string || '';
              const st = streamStatesRef.current[ti] || { accumulating: '', reasoningParts: [], complete: false };
              streamStatesRef.current[ti] = st;
              st.reasoningParts.push(content);
              setChatMessages(prev => {
                const next = [...prev];
                if (ti < next.length && next[ti].role === 'assistant') {
                  next[ti] = { ...next[ti], reasoning: st.reasoningParts.join('') };
                }
                return next;
              });
            } else if (et === 'chat.tool_generated') {
              const ti = event.turn_index as number;
              const toolName = event.tool_name as string || '';
              setChatMessages(prev => {
                const next = [...prev];
                if (ti < next.length && next[ti].role === 'assistant') {
                  const existing = next[ti].content;
                  next[ti] = { ...next[ti], content: existing ? existing + `\n\n[正在调用 ${toolName}...]` : `[正在调用 ${toolName}...]` };
                }
                return next;
              });
            } else if (et === 'chat.stream_end') {
              const ti = event.turn_index as number;
              delete streamStatesRef.current[ti];
            } else if (et === 'pipeline.edit') {
              const editId = event.edit_id as string;
              if (editId && !processedEditIdsRef.current.has(editId)) {
                processedEditIdsRef.current.add(editId);
                const edit: PendingEdit = {
                  edit_id: editId,
                  original: event.original as string || '',
                  modified: event.modified as string || '',
                  explanation: event.explanation as string || '',
                };
                setPendingEdits(prev => [...prev, edit]);
              } else if (editId) {
                setPendingEdits(prev => prev.map(e =>
                  e.edit_id === editId
                    ? { ...e,
                        modified: event.modified as string || e.modified,
                        explanation: event.explanation as string || e.explanation,
                      }
                    : e
                ));
              }
              api.listPipelines().then(r => {
                if (r.pipelines) setPipelines(r.pipelines);
              }).catch(() => {});
            } else {
              // Pipeline events
              setEvents(prev => [...prev, { type: et, timestamp: event.timestamp || (event._ts != null ? new Date(event._ts * 1000).toISOString() : new Date().toISOString()), node_name: event.step || event.pipeline || '', data: event }]);
            }

            if (et === 'chrome_disconnected') {
              console.log('[DEBUG] chrome_disconnected received, gen=%s reason=%s disconnectedRef=%s',
                connectGenRef.current, event.reason, disconnectedRef.current);
              if (disconnectedRef.current) {
                console.log('[DEBUG] chrome_disconnected already processed by another WS, skipping');
              } else {
                disconnectedRef.current = true;
                clearTimeout(connectDebounceRef.current);
                connectGenRef.current++;
                setConnected(false);
                setWsUrl('');
              }
            } else if (et === 'run_end') {
              setLoading(false);
              setCurrentRunId('');
              setCurrentPipeline('');
            }
          } catch (e) { console.log('WebSocket message parse error: %s', String(e)); }
        };
        ws.onclose = () => { if (!stopped) reconnectTimer = setTimeout(connect, 3000); };
        ws.onerror = () => { console.log('WebSocket error'); };
      } catch (e) {
        console.log('WebSocket connect failed: %s', String(e));
        if (!stopped) reconnectTimer = setTimeout(connect, 5000);
      }
    };
    connect();
    return () => { stopped = true; clearTimeout(reconnectTimer); ws?.close(); };
  }, []);

  useEffect(() => {
    if (activeTab !== 'params') return;
    api.listCredentials().then(r => {
      if (r.params) setCredKeys(r.params);
    }).catch((e) => { console.error('listCredentials failed: %s', String(e)); });
  }, [activeTab]);

  const addEvent = useCallback((type: string, node_name: string, data: Record<string, unknown> = {}) => {
    console.log('Event: %s / %s', type, node_name);
    setEvents(prev => [...prev, { type, timestamp: new Date().toISOString(), node_name, data }]);
  }, []);

  const handleRun = useCallback(async () => {
    const p = pipelines.find(t => t.name === activePreset);
    if (!p) return;

    const missingKeys: string[] = [];
    for (const key of Object.keys(p.inputs)) {
      if (!params[key]?.trim()) {
        missingKeys.push(p.inputs[key]);
      }
    }
    if (missingKeys.length > 0) {
      window.alert(t('common.missingParams', { keys: missingKeys.join(', ') }));
      return;
    }

    let pipelineContent = pipelineCache[activePreset];
    if (!pipelineContent) {
      try {
        const resp = await api.getPipeline(activePreset);
        if (resp.content) {
          pipelineContent = resp.content;
          setPipelineCache(prev => ({ ...prev, [activePreset]: pipelineContent }));
          setPipelineEditor(pipelineContent);
        } else {
          window.alert(t('common.loadFailed'));
          return;
        }
      } catch (e) {
        console.error('getPipeline failed in handleRun: %s', String(e));
        window.alert(t('common.loadFailed'));
        return;
      }
    }

    const pipelineResolved = interpolateTemplate(pipelineContent, params);
    const pipelineWithMode = pipelineResolved.replace(
      /^---\n/,
      `---\nreview_mode: "${reviewMode}"\n`
    );
    setLoading(true);
    setResult(null);
    setResultErrors(null);
    setEvents([]);
    try {
      addEvent('engine_start', 'pipeline', {});
      const resp = await api.run(pipelineWithMode, params);
      if (resp.run_id) setCurrentRunId(resp.run_id);
      if (resp.pipeline) setCurrentPipeline(resp.pipeline);
      if (resp.error) {
        addEvent('step_error', 'runner', { error: resp.error });
        setResultErrors([resp.error]);
      } else if (resp.status === 'interrupted' && resp.data?.pending_review) {
        const pr = resp.data.pending_review as {
          extra_ops: Array<{ type: string; value?: string; selector?: string }>;
          reason: string;
          guard_layer: string;
        };
        setPendingReview({
          extraOps: pr.extra_ops || [],
          reason: pr.reason || '',
          guardLayer: pr.guard_layer || '',
          threadId: resp.run_id || '',
        });
        addEvent('step_review_required', 'pipeline', { reason: pr.reason });
      } else {
        setResult(resp.data || {});
        if (resp.errors?.length) setResultErrors(resp.errors);
        addEvent('engine_end', 'pipeline', { status: resp.status });
      }
    } catch (e) {
      const msg = String(e);
      addEvent('step_error', 'runner', { error: msg });
      setResultErrors([msg]);
    } finally { setLoading(false); }
  }, [activePreset, params, pipelines, pipelineCache, addEvent, reviewMode]);

  const handleConnect = useCallback(async (mode: 'user' | 'isolated', profile?: string) => {
    disconnectedRef.current = false;
    const gen = ++connectGenRef.current;
    console.log('[DEBUG] handleConnect called mode=%s gen=%s', mode, gen);
    setConnectionError(null);
    try {
      const resp = await api.connectBrowser(mode, profile, highlightMode);
      if (gen !== connectGenRef.current) {
        console.log('[DEBUG] handleConnect gen mismatch, dropping response gen=%s current=%s', gen, connectGenRef.current);
        if (resp.success) {
          api.disconnectBrowser().catch(() => {});
        }
        return;
      }
      if (resp.needsRestart) {
        setRestartDialog({ browserName: resp.browserName || 'Chrome' });
        return;
      }
      if (resp.success) {
        console.log('[DEBUG] handleConnect success, setting connected=true gen=%s', gen);
        setWsUrl(resp.wsUrl || '');
        setConnectionError(null);
        clearTimeout(connectDebounceRef.current);
        connectDebounceRef.current = setTimeout(() => {
          if (gen === connectGenRef.current) {
            setConnected(true);
          }
        }, 300);
      } else {
        setConnectionError(resp.error || t('connection.connectionFailed'));
      }
    } catch (e) {
      if (gen !== connectGenRef.current) {
        console.log('[DEBUG] handleConnect error gen mismatch, dropping gen=%s current=%s', gen, connectGenRef.current);
        return;
      }
      console.error('Connect failed: %s', String(e));
      setConnectionError(String(e));
    }
  }, [highlightMode]);

  const handleCreateProfile = useCallback(async (name: string) => {
    if (!name.trim()) return;
    try {
      const resp = await api.createIsolatedProfile(name.trim());
      if (resp.created) {
        setProfiles(prev => {
          if (prev.includes(resp.profile_name)) return prev;
          return [...prev, resp.profile_name];
        });
        setSelectedProfile(resp.profile_name);
      } else {
        window.alert(t('common.creating') + ': ' + (resp.error || t('common.unknownError')));
      }
    } catch (e) {
      window.alert(t('common.creating') + ': ' + String(e));
    }
  }, []);

  const handleRestartConfirm = useCallback(async () => {
    disconnectedRef.current = false;
    const gen = ++connectGenRef.current;
    console.log('[DEBUG] handleRestartConfirm called gen=%s', gen);
    setRestartDialog(null);
    setRestarting(true);
    setConnectionError(null);
    try {
      const resp = await api.restartBrowser();
      if (gen !== connectGenRef.current) {
        console.log('[DEBUG] handleRestartConfirm gen mismatch, dropping response gen=%s current=%s', gen, connectGenRef.current);
        if (resp.success) {
          api.disconnectBrowser().catch(() => {});
        }
        return;
      }
      if (resp.success) {
        console.log('[DEBUG] handleRestartConfirm success, setting connected=true gen=%s', gen);
        setWsUrl(resp.wsUrl || '');
        setConnectionError(null);
        clearTimeout(connectDebounceRef.current);
        connectDebounceRef.current = setTimeout(() => {
          if (gen === connectGenRef.current) {
            setConnected(true);
          }
        }, 300);
      } else {
        setConnectionError(resp.error || 'Restart failed');
      }
    } catch (e) {
      if (gen !== connectGenRef.current) {
        console.log('[DEBUG] handleRestartConfirm error gen mismatch, dropping gen=%s current=%s', gen, connectGenRef.current);
        return;
      }
      console.error('Restart failed: %s', String(e));
      setConnectionError(String(e));
    } finally {
      setRestarting(false);
    }
  }, []);

  const handleRestartIsolated = useCallback(() => {
    setRestartDialog(null);
    handleConnect('isolated', selectedProfile);
  }, [handleConnect, selectedProfile]);

  const handleRestartCancel = useCallback(() => {
    setRestartDialog(null);
  }, []);

  const refreshPipeline = useCallback(async () => {
    if (!activePreset || activePreset === '__chat__') return;
    try {
      const resp = await api.getPipeline(activePreset);
      if (resp.content) {
        setPipelineCache(prev => ({ ...prev, [activePreset]: resp.content }));
        setPipelineEditor(resp.content);
      }
    } catch (e) { console.error('refreshPipeline failed: %s', String(e)); }
  }, [activePreset]);

  const handleChatConfirm = useCallback(async (editId: string): Promise<string | null> => {
    try {
      const result = await api.chatConfirm(editId);
      if (result.status === 'confirmed' || result.status === 'already_confirmed') {
        await refreshPipeline();
        setPendingEdits(prev => prev.filter(e => e.edit_id !== editId));
        return null;
      }
      return result.error || 'Confirm failed';
    } catch (e) {
      return String(e);
    }
  }, [refreshPipeline]);

  const handleChatRevert = useCallback(async (editId: string): Promise<string | null> => {
    try {
      const result = await api.chatRevert(editId);
      if (result.status === 'reverted' || result.status === 'already_reverted') {
        await refreshPipeline();
        setPendingEdits(prev => prev.filter(e => e.edit_id !== editId));
        return null;
      }
      return result.error || 'Revert failed';
    } catch (e) {
      return String(e);
    }
  }, [refreshPipeline]);

  const handleDisconnect = useCallback(async () => {
    console.log('[DEBUG] handleDisconnect called');
    try {
      await api.disconnectBrowser();
    } catch (e) {
      console.error('Disconnect failed: %s', String(e));
    }
    setConnected(false);
    setWsUrl('');
    setConnectionError(null);
  }, []);

  const handleParamChange = useCallback((key: string, value: string) => {
    setParams(prev => ({ ...prev, [key]: value }));
  }, []);

  const handleCancel = useCallback(async () => {
    if (!currentPipeline || !currentRunId) return;
    setCancelling(true);
    try {
      await api.cancelPipeline(currentPipeline, currentRunId);
      setLoading(false);
      setCurrentRunId('');
      setCurrentPipeline('');
    } catch (e) {
      console.error('Cancel failed: %s', String(e));
    } finally {
      setCancelling(false);
    }
  }, [currentPipeline, currentRunId]);

  const handleReviewApprove = useCallback(async (reason: string) => {
    const pr = pendingReview;
    setPendingReview(null);
    if (pr?.threadId) {
      try {
        await api.reviewPipeline(pr.threadId, 'approve', reason);
      } catch (e) {
        console.error('Review approve failed: %s', String(e));
      }
    }
    addEvent('resume', 'pipeline', { action: 'approve', reason });
  }, [addEvent, pendingReview]);

  const handleReviewReject = useCallback(async (reason: string) => {
    const pr = pendingReview;
    setPendingReview(null);
    if (pr?.threadId) {
      try {
        await api.reviewPipeline(pr.threadId, 'reject', reason);
      } catch (e) {
        console.error('Review reject failed: %s', String(e));
      }
    }
    addEvent('resume', 'pipeline', { action: 'reject', reason });
  }, [addEvent, pendingReview]);

  const handleCredSet = useCallback(async () => {
    if (!credKey.trim() || !credValue.trim()) return;
    await api.setCredential(credKey.trim(), credValue);
    setCredKey('');
    setCredValue('');
    const r = await api.listCredentials();
    if (r.params) setCredKeys(r.params);
  }, [credKey, credValue]);

  const handleCredDelete = useCallback(async (key: string) => {
    await api.deleteCredential(key);
    setCredKeys(prev => prev.filter(k => k !== key));
  }, []);

  const handleRefreshPipelines = useCallback(async () => {
    const r = await api.listPipelines();
    if (r.pipelines) setPipelines(r.pipelines);
  }, []);

  const handleDeletePipeline = useCallback(async (name: string) => {
    const r = await api.deletePipeline(name);
    if (r.ok) {
      if (activePreset === name) {
        switchPipeline('__chat__');
        setPipelineEditor('');
      }
      handleRefreshPipelines();
    } else {
      window.alert(r.error || 'Delete failed');
    }
  }, [activePreset, handleRefreshPipelines, switchPipeline]);

  const handleSavePipeline = useCallback(async () => {
    if (!activePreset || activePreset === '__chat__' || !pipelineEditor.trim()) return;
    try {
      const r = await api.savePipeline(activePreset, pipelineEditor);
      if (r.ok) {
        setPipelineCache(prev => ({ ...prev, [activePreset]: pipelineEditor }));
        handleRefreshPipelines();
      } else {
        window.alert(r.error || 'Save failed');
      }
    } catch (e) {
      window.alert(String(e));
    }
  }, [activePreset, pipelineEditor, handleRefreshPipelines]);

  const preset = pipelines.find(p => p.name === activePreset);
  const stages = preset?.stages ?? [];

  const stepNames = stages.length > 0 ? stages
    : events.filter(e => e.type === 'step_start').map(e => e.node_name);

  const getStepStatus = (name: string): 'done' | 'current' | 'pending' | 'error' | 'review' => {
    const hasStart = events.some(e => e.type === 'step_start' && e.node_name === name);
    const hasEnd = events.some(e => e.type === 'step_end' && e.node_name === name);
    const hasError = events.some(e => e.type === 'step_error' && e.node_name === name);
    const hasReview = events.some(e => e.type === 'step_review_required' && e.node_name === name);
    if (hasError) return 'error';
    if (pendingReview && hasStart && !hasEnd) return 'review';
    if (hasStart && hasEnd) return 'done';
    if (hasStart && !hasEnd) return 'current';
    return 'pending';
  };

  const stepStarts = events.filter(e => e.type === 'step_start');
  const stepEnds = events.filter(e => e.type === 'step_end');

  const treeNodes: TreeNode[] = [
    {
      name: '__chat__',
      label: t('chat.noWorkspace', 'No Workspace'),
      isPipeline: false,
      sessions: chatSessions,
    },
    ...pipelines.map(p => ({
      name: p.name,
      label: p.title || p.name,
      isPipeline: true,
      sessions: pipelineSessions[p.name] || [],
    })),
  ];

  return (
    <div className="app-container">
      <TitleBar />
      {restartDialog && (
        <div className="modal-overlay" onClick={handleRestartCancel}>
          <div className="modal-box" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <span className="modal-icon">⚠</span>
              <span>{t('restartDialog.title')}</span>
            </div>
            <div className="modal-body">
              <p><strong>{restartDialog.browserName}</strong> is running but debug mode is not enabled.</p>
              <p>To connect to a user browser, close and restart {restartDialog.browserName} (with debug port).</p>
              {restarting && <p className="modal-loading">{t('restartDialog.restarting', { browserName: restartDialog.browserName })}</p>}
            </div>
            <div className="modal-footer">
              <button className="btn btn-secondary" onClick={handleRestartCancel} disabled={restarting}>{t('restartDialog.cancel')}</button>
              <button className="btn btn-secondary" onClick={handleRestartIsolated} disabled={restarting}>{t('restartDialog.useIsolated')}</button>
              <button className="btn btn-primary" onClick={handleRestartConfirm} disabled={restarting}>
                {restarting ? t('restartDialog.restarting', { browserName: restartDialog.browserName }) : t('restartDialog.closeAndRestart')}
              </button>
            </div>
          </div>
        </div>
      )}
      <ConnectionBar
        connected={connected}
        wsUrl={wsUrl}
        connectionError={connectionError}
        connectMode={connectMode}
        selectedProfile={selectedProfile}
        onConnect={handleConnect}
        onDisconnect={handleDisconnect}
        onModeChange={(mode) => { setConnectMode(mode); setConnectionError(null); }}
        onProfileChange={setSelectedProfile}
        profiles={profiles}
        onCreateProfile={handleCreateProfile}
      />

      <div className="tab-bar">
        <div className={`tab ${activeTab === 'exec' ? 'active' : ''}`} onClick={() => setActiveTab('exec')}>
          <span className="tab-icon">🎯</span> {t('tabs.run')}
          {loading && <span className="tab-badge">{t('tabs.running')}</span>}
        </div>
        <div className={`tab ${activeTab === 'agentmd' ? 'active' : ''}`} onClick={() => setActiveTab('agentmd')}>
          <span className="tab-icon">💬</span> {t('tabs.chat')}
        </div>
        <div className={`tab ${activeTab === 'log' ? 'active' : ''}`} onClick={() => setActiveTab('log')}>
          <span className="tab-icon">📋</span> {t('tabs.log')}
          {pendingReview && <span className="tab-dot" />}
        </div>
        <div className="tab-spacer" />
        <div className={`tab ${activeTab === 'pipelines' ? 'active' : ''}`} onClick={() => setActiveTab('pipelines')}>
          <span className="tab-icon">📦</span> {t('tabs.pipelines')}
        </div>
        <div className={`tab ${activeTab === 'params' ? 'active' : ''}`} onClick={() => setActiveTab('params')}>
          <span className="tab-icon">⚙</span> {t('tabs.params')}
        </div>
        <div className={`tab ${activeTab === 'settings' ? 'active' : ''}`} onClick={() => setActiveTab('settings')}>
          <span className="tab-icon">⚙</span> {t('tabs.settings')}
        </div>
      </div>

      <div className="tab-content" style={{ display: activeTab === 'exec' ? 'flex' : 'none' }}>
        <ExecTab
          activePreset={activePreset} setActivePreset={setActivePreset}
          pipelines={pipelines} loading={loading} connected={connected}
          currentRunId={currentRunId} cancelling={cancelling}
          preset={preset} params={params} pendingReview={pendingReview}
          stages={stages} events={events}
          result={result} resultErrors={resultErrors}
          onRun={handleRun} onParamChange={handleParamChange}
          onCancel={handleCancel}
          onReviewApprove={handleReviewApprove}
          onReviewReject={handleReviewReject}
          onTabChange={setActiveTab}
        />
      </div>

      <div className="tab-content" style={{ display: activeTab === 'agentmd' ? 'flex' : 'none' }}>
        <ChatTab
          treeNodes={treeNodes}
          expandedNodes={expandedNodes}
          onToggleExpand={handleToggleExpand}
          sidebarCollapsed={sidebarCollapsed}
          onToggleSidebar={toggleSidebar}
          messages={chatMessages}
          setMessages={setChatMessages}
          connected={connected}
          activePreset={activePreset}
          currentSessionId={currentSessionId}
          loadingSession={loadingSession}
          onNewSession={async () => {
            setLoadingSession(true);
            try {
              const r = await api.newSession(activePreset);
              if (r.session_id) {
                setCurrentSessionId(r.session_id);
                setChatMessages([]);
                const list = await api.listSessions(activePreset);
                const sessionsList = list.sessions || [];
                if (activePreset === '__chat__' || !activePreset) {
                  setChatSessions(sessionsList);
                } else {
                  setPipelineSessions(prev => ({ ...prev, [activePreset]: sessionsList }));
                }
              }
            } catch (e) {
              console.error('newSession failed: %s', String(e));
            } finally {
              setLoadingSession(false);
            }
          }}
          onArchiveSession={async (sessionId: string) => {
            if (!confirm(t('chat.archiveSessionConfirm', 'Archive this session?'))) return;
            try {
              await api.archiveSession(activePreset, sessionId);
              const list = await api.listSessions(activePreset);
              const sessionsList = list.sessions || [];
              if (activePreset === '__chat__' || !activePreset) {
                setChatSessions(sessionsList);
              } else {
                setPipelineSessions(prev => ({ ...prev, [activePreset]: sessionsList }));
              }
              if (currentSessionId === sessionId) {
                const found = sessionsList.find(s => s.session_id !== sessionId);
                setCurrentSessionId(found?.session_id || '');
              }
            } catch (e) {
              console.error('archiveSession failed: %s', String(e));
            }
          }}
          onSelectSession={async (sessionId: string) => {
            setLoadingSession(true);
            try {
              const r = await api.getSessionData(activePreset, sessionId);
              if (r.session) {
                setCurrentSessionId(sessionId);
                setChatMessages(r.session.messages || []);
              }
            } catch (e) {
              console.error('getSessionData failed: %s', String(e));
            } finally {
              setLoadingSession(false);
            }
          }}
          pipelineEditor={pipelineEditor}
          onPipelineEditorChange={setPipelineEditor}
          onRefreshPipeline={refreshPipeline}
          pendingEdit={activePendingEdit}
          onConfirmEdit={handleChatConfirm}
          onRevertEdit={handleChatRevert}
          onDeletePipeline={handleDeletePipeline}
          onSavePipeline={handleSavePipeline}
          reversed={chatLayoutReversed}
          theme={theme}
        />
      </div>

      <div className="tab-content" style={{ display: activeTab === 'log' ? 'flex' : 'none' }}>
        <LogTab
          currentRunId={currentRunId}
          stepNames={stepNames}
          getStepStatus={getStepStatus}
          events={events}
          onClearEvents={() => setEvents([])}
          result={result} resultErrors={resultErrors}
          loading={loading}
          stepStarts={stepStarts} stepEnds={stepEnds}
          preset={preset}
          pendingReview={pendingReview}
          onReviewApprove={handleReviewApprove}
          onReviewReject={handleReviewReject}
        />
      </div>

      <div className="tab-content" style={{ display: activeTab === 'pipelines' ? 'flex' : 'none' }}>
        <PipelinesTab
          pipelines={pipelines}
          onRefresh={handleRefreshPipelines}
          onSelectPreset={setActivePreset}
          onTabChange={setActiveTab}
          onDeletePipeline={handleDeletePipeline}
        />
      </div>

      <div className="tab-content" style={{ display: activeTab === 'params' ? 'flex' : 'none' }}>
        <ParamsTab
          credKeys={credKeys}
          credKey={credKey} onCredKeyChange={setCredKey}
          credValue={credValue} onCredValueChange={setCredValue}
          onCredSet={handleCredSet}
          onCredDelete={handleCredDelete}
        />
      </div>

      <div className="tab-content" style={{ display: activeTab === 'settings' ? 'flex' : 'none' }}>
        <SettingsTab
          reviewMode={reviewMode} onReviewModeChange={setReviewMode}
          chatLayoutReversed={chatLayoutReversed}
          onChatLayoutReversedChange={(v) => {
            setChatLayoutReversed(v);
            try { localStorage.setItem('chat-layout-reversed', String(v)); } catch { /* ok */ }
          }}
          theme={theme} onThemeChange={setThemePersist}
          highlightMode={highlightMode}
          onHighlightModeChange={(mode) => {
            setHighlightMode(mode);
            try { localStorage.setItem('highlight-mode', mode); } catch { /* ok */ }
          }}
        />
      </div>

      <StatusBar events={events} connected={connected} />
    </div>
  );
}
