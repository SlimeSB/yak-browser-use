import React, { useState, useCallback, useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import './styles/global.css';
import { getLogger } from '../utils/logger';
import type { PipelineMeta, EventData, ChatMessage, PendingEdit } from './types';
import TitleBar from './components/TitleBar';
import ConnectionBar from './components/ConnectionBar';
import StatusBar from './components/StatusBar';
import ExecTab from './components/tabs/ExecTab';
import ChatTab from './components/tabs/ChatTab';
import LogTab from './components/tabs/LogTab';
import PipelinesTab from './components/tabs/PipelinesTab';
import ParamsTab from './components/tabs/ParamsTab';
import SettingsTab from './components/tabs/SettingsTab';

const logger = getLogger('App');

function interpolateTemplate(template: string, ctx: Record<string, string>): string {
  return template.replace(/{{(\w+)}}/g, (_match, key: string) => ctx[key] ?? `{{${key}}}`);
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
  const [connectMode, setConnectMode] = useState<'user' | 'isolated'>('user');
  const [selectedProfile, setSelectedProfile] = useState(t('common.defaultTemp'));
  const [profiles, setProfiles] = useState<string[]>([t('common.defaultTemp')]);
  const [params, setParams] = useState<Record<string, string>>({});
  const [restartDialog, setRestartDialog] = useState<{ browserName: string } | null>(null);
  const [restarting, setRestarting] = useState(false);
  const [reviewMode, setReviewMode] = useState('human');
  const [currentRunId, setCurrentRunId] = useState('');
  const [currentPipeline, setCurrentPipeline] = useState('');
  const [cancelling, setCancelling] = useState(false);
  const [credKeys, setCredKeys] = useState<string[]>([]);
  const [credKey, setCredKey] = useState('');
  const [credValue, setCredValue] = useState('');

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

  const activePendingEdit = pendingEdits.length > 0 ? pendingEdits[0] : null;

  const [pipelineEditor, setPipelineEditor] = useState('');
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [chatInput, setChatInput] = useState('');
  const [chatSending, setChatSending] = useState(false);
  const [streamingMsg, setStreamingMsg] = useState('');
  const [sessionStatus, setSessionStatus] = useState('idle');
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    window.electronAPI.listPipelines().then(r => {
      if (r.pipelines && r.pipelines.length > 0) {
        setPipelines(r.pipelines);
        if (!activePreset) setActivePreset(r.pipelines[0].name);
      }
    }).catch((e) => { logger.error('listPipelines failed: %s', String(e)); });
  }, []);

  useEffect(() => {
    window.electronAPI.listIsolatedProfiles().then(r => {
      if (r.profiles && r.profiles.length > 0) {
        setProfiles(r.profiles);
      }
    }).catch((e) => { logger.error('listIsolatedProfiles failed: %s', String(e)); });
  }, []);

  useEffect(() => {
    const preset = pipelines.find(p => p.name === activePreset);
    if (preset) {
      let pipelineContent = pipelineCache[activePreset];
      if (pipelineContent) {
        setPipelineEditor(pipelineContent);
      } else {
        window.electronAPI.getPipeline(activePreset).then(resp => {
          if (resp.agent_md) {
            setPipelineCache(prev => ({ ...prev, [activePreset]: resp.agent_md }));
            setPipelineEditor(resp.agent_md);
          }
    }).catch((e) => { logger.error('getPipeline failed: %s', String(e)); });
      }
    }
  }, [activePreset, pipelines]);

  useEffect(() => {
    const preset = pipelines.find(p => p.name === activePreset);
    if (preset) {
      const init: Record<string, string> = {};
      for (const key of Object.keys(preset.inputs)) {
        init[key] = preset.defaults?.[key] ?? '';
      }
      setParams(init);
    }
    setResult(null);
    setResultErrors(null);
    setEvents([]);
  }, [activePreset, pipelines]);

  useEffect(() => {
    if (connected) return;
    let timer: ReturnType<typeof setTimeout>;
    let delay = 5000;
    const check = async () => {
      try {
        const s = await window.electronAPI.chromeStatus();
        if (s.connected) {
          setConnected(true);
          setWsUrl(s.ws_url || '');
          setConnectionError(null);
          return;
        }
        delay = 5000;
      } catch (e) {
        logger.debug('chromeStatus poll failed: %s', String(e));
        delay = Math.min(delay * 2, 60_000);
      }
      timer = setTimeout(check, delay);
    };
    timer = setTimeout(check, 1000);
    return () => clearTimeout(timer);
  }, [connected]);

  useEffect(() => {
    let ws: WebSocket | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout>;
    const connect = async () => {
      try {
        const port = await window.electronAPI.getPort();
        ws = new WebSocket(`ws://127.0.0.1:${port}/ws/events`);
        ws.onmessage = (ev) => {
          try {
            const event = JSON.parse(ev.data);
            const et = event.type;

            // Chat events
            if (et === 'chat.message') {
              const c = event.content as string;
              setChatMessages(prev => [...prev, { role: 'assistant', content: c || '' }]);
            } else if (et === 'chat.tool_start') {
              setChatMessages(prev => [...prev, {
                role: 'tool',
                content: '',
                toolName: event.tool_name || '',
                toolOk: undefined,
              }]);
            } else if (et === 'chat.tool_end') {
              setChatMessages(prev => {
                const next = [...prev];
                for (let i = next.length - 1; i >= 0; i--) {
                  if (next[i].role === 'tool' && next[i].toolName === event.tool_name && next[i].toolOk === undefined) {
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
            } else if (et === 'chat.error') {
              setChatMessages(prev => [...prev, { role: 'assistant', content: `[Error] ${event.message || ''}` }]);
            } else if (et === 'session.state') {
              setSessionStatus(event.status || '');
              if (event.status === 'completed' || event.status === 'cancelled') {
                setChatSending(false);
              }
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
            } else {
              // Pipeline events
              setEvents(prev => [...prev, { type: et, timestamp: event.timestamp, node_name: event.step || event.pipeline || '', data: event }]);
            }

            if (et === 'run_end') {
              setLoading(false);
              setCurrentRunId('');
              setCurrentPipeline('');
            }
          } catch (e) { logger.debug('WebSocket message parse error: %s', String(e)); }
        };
        ws.onclose = () => { reconnectTimer = setTimeout(connect, 3000); };
        ws.onerror = () => { ws?.close(); };
      } catch (e) {
        logger.debug('WebSocket connect failed: %s', String(e));
        reconnectTimer = setTimeout(connect, 5000);
      }
    };
    connect();
    return () => { clearTimeout(reconnectTimer); ws?.close(); };
  }, []);

  useEffect(() => {
    if (activeTab !== 'params') return;
    window.electronAPI.listCredentials().then(r => {
      if (r.credentials) setCredKeys(r.credentials);
    }).catch((e) => { logger.error('listCredentials failed: %s', String(e)); });
  }, [activeTab]);

  const addEvent = useCallback((type: string, node_name: string, data: Record<string, unknown> = {}) => {
    logger.debug('Event: %s / %s', type, node_name);
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
      window.electronAPI.showAlert(t('common.missingParams', { keys: missingKeys.join(', ') }));
      return;
    }

    let pipelineContent = pipelineCache[activePreset];
    if (!pipelineContent) {
      try {
        const resp = await window.electronAPI.getPipeline(activePreset);
        if (resp.agent_md) {
          pipelineContent = resp.agent_md;
          setPipelineCache(prev => ({ ...prev, [activePreset]: pipelineContent }));
          setPipelineEditor(pipelineContent);
        } else {
          window.electronAPI.showAlert(t('common.loadFailed'));
          return;
        }
      } catch (e) {
        logger.error('getPipeline failed in handleRun: %s', String(e));
        window.electronAPI.showAlert(t('common.loadFailed'));
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
      const resp = await window.electronAPI.run(pipelineWithMode, params);
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
    setConnectionError(null);
    try {
      const resp = await window.electronAPI.connectBrowser(mode, profile);
      if (resp.needsRestart) {
        setRestartDialog({ browserName: resp.browserName || 'Chrome' });
        return;
      }
      if (resp.success) {
        setConnected(true);
        setWsUrl(resp.wsUrl || '');
        setConnectionError(null);
      } else {
        setConnectionError(resp.error || t('connection.connectionFailed'));
      }
    } catch (e) {
      logger.error('Connect failed: %s', String(e));
      setConnectionError(String(e));
    }
  }, []);

  const handleCreateProfile = useCallback(async (name: string) => {
    if (!name.trim()) return;
    try {
      const resp = await window.electronAPI.createIsolatedProfile(name.trim());
      if (resp.created) {
        setProfiles(prev => {
          if (prev.includes(resp.profile_name)) return prev;
          return [...prev, resp.profile_name];
        });
        setSelectedProfile(resp.profile_name);
      } else {
        window.electronAPI.showAlert(t('common.creating') + ': ' + (resp.error || t('common.unknownError')));
      }
    } catch (e) {
      window.electronAPI.showAlert(t('common.creating') + ': ' + String(e));
    }
  }, []);

  const handleRestartConfirm = useCallback(async () => {
    setRestartDialog(null);
    setRestarting(true);
    setConnectionError(null);
    try {
      const resp = await window.electronAPI.restartBrowser();
      if (resp.success) {
        setConnected(true);
        setWsUrl(resp.wsUrl || '');
        setConnectionError(null);
      } else {
        setConnectionError(resp.error || t('connection.restartFailed'));
      }
    } catch (e) {
      logger.error('Restart failed: %s', String(e));
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

  const handleChatSend = useCallback(async () => {
    if (!chatInput.trim() || chatSending) return;
    const userMsg = chatInput.trim();
    setChatInput('');
    setChatMessages(prev => [...prev, { role: 'user', content: userMsg }]);
    setChatSending(true);

    try {
      const result = await window.electronAPI.chat(userMsg);
      if (result.ok) {
        const resp = result.response;
        if (resp) {
          setChatMessages(prev => [...prev, { role: 'assistant', content: resp }]);
        }
      } else {
        setChatMessages(prev => [...prev, { role: 'assistant', content: `Error: ${result.error || 'Unknown'}` }]);
      }
    } catch (e) {
      setChatMessages(prev => [...prev, { role: 'assistant', content: `Error: ${String(e)}` }]);
    } finally {
      setChatSending(false);
    }
  }, [chatInput, chatSending]);

  const streamingMsgRef = useRef('');
  useEffect(() => { streamingMsgRef.current = streamingMsg; }, [streamingMsg]);

  const refreshPipeline = useCallback(async () => {
    if (!activePreset) return;
    try {
      const resp = await window.electronAPI.getPipeline(activePreset);
      if (resp.agent_md) {
        setPipelineCache(prev => ({ ...prev, [activePreset]: resp.agent_md }));
        setPipelineEditor(resp.agent_md);
      }
    } catch (e) { logger.error('refreshPipeline failed: %s', String(e)); }
  }, [activePreset]);

  const handleChatConfirm = useCallback(async (editId: string): Promise<string | null> => {
    try {
      const result = await window.electronAPI.chatConfirm(editId);
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
      const result = await window.electronAPI.chatRevert(editId);
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
    try {
      await window.electronAPI.disconnectBrowser();
    } catch (e) {
      logger.error('Disconnect failed: %s', String(e));
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
      await window.electronAPI.cancelPipeline(currentPipeline, currentRunId);
      setLoading(false);
      setCurrentRunId('');
      setCurrentPipeline('');
    } catch (e) {
      logger.error('Cancel failed: %s', String(e));
    } finally {
      setCancelling(false);
    }
  }, [currentPipeline, currentRunId]);

  const handleReviewApprove = useCallback(async (reason: string) => {
    const pr = pendingReview;
    setPendingReview(null);
    if (pr?.threadId) {
      try {
        await window.electronAPI.reviewPipeline(pr.threadId, 'approve', reason);
      } catch (e) {
        logger.error('Review approve failed: %s', String(e));
      }
    }
    addEvent('resume', 'pipeline', { action: 'approve', reason });
  }, [addEvent, pendingReview]);

  const handleReviewReject = useCallback(async (reason: string) => {
    const pr = pendingReview;
    setPendingReview(null);
    if (pr?.threadId) {
      try {
        await window.electronAPI.reviewPipeline(pr.threadId, 'reject', reason);
      } catch (e) {
        logger.error('Review reject failed: %s', String(e));
      }
    }
    addEvent('resume', 'pipeline', { action: 'reject', reason });
  }, [addEvent, pendingReview]);

  const handleCredSet = useCallback(async () => {
    if (!credKey.trim() || !credValue.trim()) return;
    await window.electronAPI.setCredential(credKey.trim(), credValue);
    setCredKey('');
    setCredValue('');
    const r = await window.electronAPI.listCredentials();
    if (r.credentials) setCredKeys(r.credentials);
  }, [credKey, credValue]);

  const handleCredDelete = useCallback(async (key: string) => {
    await window.electronAPI.deleteCredential(key);
    setCredKeys(prev => prev.filter(k => k !== key));
  }, []);

  const handleRefreshPipelines = useCallback(async () => {
    const r = await window.electronAPI.listPipelines();
    if (r.pipelines) setPipelines(r.pipelines);
  }, []);

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
          messages={chatMessages}
          setMessages={setChatMessages}
          connected={connected}
          pipelines={pipelines}
          activePreset={activePreset}
          onPresetChange={setActivePreset}
          pipelineEditor={pipelineEditor}
          onPipelineEditorChange={setPipelineEditor}
          onRefreshPipeline={refreshPipeline}
          pendingEdit={activePendingEdit}
          onConfirmEdit={handleChatConfirm}
          onRevertEdit={handleChatRevert}
          reversed={chatLayoutReversed}
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
        />
      </div>

      <StatusBar events={events} connected={connected} />
    </div>
  );
}
