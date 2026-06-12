import React, { useState, useCallback, useEffect, useRef } from 'react';
import './styles/global.css';
import { getLogger } from '../../utils/logger';
import type { PipelineMeta, EventData, ChatPendingDiff, DiffLine } from './types';
import TitleBar from './components/TitleBar';
import ConnectionBar from './components/ConnectionBar';
import StatusBar from './components/StatusBar';
import ExecTab from './components/tabs/ExecTab';
import AgentMdTab from './components/tabs/AgentMdTab';
import LogTab from './components/tabs/LogTab';
import PipelinesTab from './components/tabs/PipelinesTab';
import ParamsTab from './components/tabs/ParamsTab';
import SettingsTab from './components/tabs/SettingsTab';

const logger = getLogger('App');

function interpolateTemplate(template: string, ctx: Record<string, string>): string {
  return template.replace(/{{(\w+)}}/g, (_match, key: string) => ctx[key] ?? `{{${key}}}`);
}

export default function App() {
  const [activeTab, setActiveTab] = useState('exec');
  const [pipelines, setPipelines] = useState<PipelineMeta[]>([]);
  const [events, setEvents] = useState<EventData[]>([]);
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [resultErrors, setResultErrors] = useState<string[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [activePreset, setActivePreset] = useState('');
  const [agentMdCache, setAgentMdCache] = useState<Record<string, string>>({});
  const [connected, setConnected] = useState(false);
  const [wsUrl, setWsUrl] = useState('');
  const [connectionError, setConnectionError] = useState<string | null>(null);
  const [connectMode, setConnectMode] = useState<'user' | 'isolated'>('user');
  const [selectedProfile, setSelectedProfile] = useState('默认临时目录');
  const [profiles, setProfiles] = useState<string[]>(['默认临时目录']);
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

  const [pendingReview, setPendingReview] = useState<{
    extraOps: Array<{ type: string; value?: string; selector?: string }>;
    reason: string;
    guardLayer: string;
    threadId: string;
  } | null>(null);

  const [agentMdEditor, setAgentMdEditor] = useState('');
  const [chatMessages, setChatMessages] = useState<Array<{role: string; content: string}>>([
    {role: 'system', content: '选择上方管线后，可以用对话修改 agent.md。也可以直接改右侧编辑器。'}
  ]);
  const [chatInput, setChatInput] = useState('');
  const [chatSending, setChatSending] = useState(false);
  const [chatPendingDiffs, setChatPendingDiffs] = useState<ChatPendingDiff[]>([]);
  const [streamingMsg, setStreamingMsg] = useState('');
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
      let agentMd = agentMdCache[activePreset];
      if (agentMd) {
        setAgentMdEditor(agentMd);
      } else {
        window.electronAPI.getPipeline(activePreset).then(resp => {
          if (resp.agent_md) {
            setAgentMdCache(prev => ({ ...prev, [activePreset]: resp.agent_md }));
            setAgentMdEditor(resp.agent_md);
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
            setEvents(prev => [...prev, { type: event.type, timestamp: event.timestamp, node_name: event.step || event.pipeline || '', data: event }]);
            if (event.type === 'run_end') {
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
      window.electronAPI.showAlert(`请填写以下参数：${missingKeys.join('、')}`);
      return;
    }

    let agentMd = agentMdCache[activePreset];
    if (!agentMd) {
      try {
        const resp = await window.electronAPI.getPipeline(activePreset);
        if (resp.agent_md) {
          agentMd = resp.agent_md;
          setAgentMdCache(prev => ({ ...prev, [activePreset]: agentMd }));
          setAgentMdEditor(agentMd);
        } else {
          window.electronAPI.showAlert('无法加载管线定义');
          return;
        }
      } catch (e) {
        logger.error('getPipeline failed in handleRun: %s', String(e));
        window.electronAPI.showAlert('加载管线定义失败');
        return;
      }
    }

    const agentMdResolved = interpolateTemplate(agentMd, params);
    const agentMdWithMode = agentMdResolved.replace(
      /^---\n/,
      `---\nreview_mode: "${reviewMode}"\n`
    );
    setLoading(true);
    setResult(null);
    setResultErrors(null);
    setEvents([]);
    try {
      addEvent('engine_start', 'pipeline', {});
      const resp = await window.electronAPI.run(agentMdWithMode, params);
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
  }, [activePreset, params, pipelines, agentMdCache, addEvent, reviewMode]);

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
        setConnectionError(resp.error || '连接失败，请检查 Chrome 是否正在运行');
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
        window.electronAPI.showAlert('创建失败: ' + (resp.error || '未知错误'));
      }
    } catch (e) {
      window.electronAPI.showAlert('创建失败: ' + String(e));
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
        setConnectionError(resp.error || '重启失败');
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
    if (!chatInput.trim() || chatSending || !activePreset) return;
    const userMsg = chatInput.trim();
    setChatInput('');
    setChatMessages(prev => [...prev, { role: 'user', content: userMsg }]);
    setChatSending(true);
    setStreamingMsg('');

    if (esRef.current) {
      esRef.current.close();
      esRef.current = null;
    }

    try {
      const port = await window.electronAPI.getPort();
      const encodedMsg = encodeURIComponent(userMsg);
      const url = `http://127.0.0.1:${port}/api/chat/agent/${activePreset}/stream?message=${encodedMsg}`;
      const es = new EventSource(url);
      esRef.current = es;

      es.addEventListener('tool_start', (e: MessageEvent) => {
        try {
          const data = JSON.parse(e.data);
          setChatMessages(prev => [...prev, {
            role: 'tool',
            content: `🔧 ${data.name}`,
          }]);
        } catch (e) { logger.debug('SSE tool_start parse error: %s', String(e)); }
      });

      es.addEventListener('tool_end', (e: MessageEvent) => {
        try {
          const data = JSON.parse(e.data);
          const result = data.result;
          const ok = result && !result.error;
          setChatMessages(prev => {
            const msgs = [...prev];
            const lastTool = [...msgs].reverse().find(m => m.role === 'tool');
            if (lastTool) {
              const idx = msgs.indexOf(lastTool);
              msgs[idx] = {
                role: 'tool',
                content: `${ok ? '✓' : '✗'} ${data.name}${result?.error ? ': ' + result.error : ''}`,
              };
            }
            return msgs;
          });
        } catch (e) { logger.debug('SSE tool_end parse error: %s', String(e)); }
      });

      es.addEventListener('patch_applied', (e: MessageEvent) => {
        try {
          const data = JSON.parse(e.data);
          const diffLines: DiffLine[] = (data.diff || []).map((d: Record<string, unknown>) => ({
            type: (d.type as 'add' | 'del' | 'ctx') || 'ctx',
            line: (d.line as string) || '',
            oldLineNum: d.oldLineNum as number | undefined,
            newLineNum: d.newLineNum as number | undefined,
            highlights: d.highlights as DiffLine['highlights'],
          }));
          setChatPendingDiffs(prev => [...prev, {
            id: data.id || '',
            explanation: data.explanation || '',
            action: data.action || '',
            diff: diffLines,
          }]);
        } catch (e) { logger.debug('SSE patch_applied parse error: %s', String(e)); }
      });

      es.addEventListener('response', (e: MessageEvent) => {
        try {
          const data = JSON.parse(e.data);
          setStreamingMsg(prev => prev + data);
        } catch (e) { logger.debug('SSE response parse error: %s', String(e)); }
      });

      es.addEventListener('done', (e: MessageEvent) => {
        if (streamingMsgRef.current) {
          setChatMessages(prev => [...prev, { role: 'assistant', content: streamingMsgRef.current }]);
          setStreamingMsg('');
        }
        setChatSending(false);
        es.close();
        esRef.current = null;
      });

      es.addEventListener('error', () => {
        if (streamingMsgRef.current) {
          setChatMessages(prev => [...prev, { role: 'assistant', content: streamingMsgRef.current }]);
          setStreamingMsg('');
        }
        setChatMessages(prev => [...prev, { role: 'assistant', content: '连接中断或请求失败' }]);
        setChatSending(false);
        es.close();
        esRef.current = null;
      });
    } catch (e) {
      setChatMessages(prev => [...prev, { role: 'assistant', content: `请求失败: ${String(e)}` }]);
      setChatSending(false);
    }
  }, [chatInput, chatSending, activePreset]);

  const streamingMsgRef = useRef('');
  useEffect(() => { streamingMsgRef.current = streamingMsg; }, [streamingMsg]);

  const refreshAgentMd = useCallback(async () => {
    if (!activePreset) return;
    try {
      const resp = await window.electronAPI.getPipeline(activePreset);
      if (resp.agent_md) {
        setAgentMdCache(prev => ({ ...prev, [activePreset]: resp.agent_md }));
        setAgentMdEditor(resp.agent_md);
      }
    } catch (e) { logger.error('refreshAgentMd failed: %s', String(e)); }
  }, [activePreset]);

  const handleChatDismiss = useCallback(async (index: number) => {
    const item = chatPendingDiffs[index];
    if (!item || !item.id) return;
    try {
      await fetch(`http://127.0.0.1:${await window.electronAPI.getPort()}/api/chat/agent/${activePreset}/patch/${item.id}/dismiss`, { method: 'POST' });
    } catch (e) { logger.error('handleChatDismiss failed: %s', String(e)); }
    setChatPendingDiffs(prev => prev.filter((_, i) => i !== index));
    await refreshAgentMd();
  }, [chatPendingDiffs, activePreset, refreshAgentMd]);

  const handleChatRollback = useCallback(async (index: number) => {
    const item = chatPendingDiffs[index];
    if (!item || !item.id) return;
    let removedCount = 1;
    try {
      const port = await window.electronAPI.getPort();
      const resp = await fetch(`http://127.0.0.1:${port}/api/chat/agent/${activePreset}/patch/${item.id}/rollback`, { method: 'POST' });
      const data = await resp.json();
      removedCount = data.removed_count || 1;
    } catch (e) { logger.error('handleChatRollback failed: %s', String(e)); }
    setChatPendingDiffs(prev => prev.filter((_, i) => i < index || i >= index + removedCount));
    await refreshAgentMd();
  }, [chatPendingDiffs, activePreset, refreshAgentMd]);

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
              <span>需要重启浏览器</span>
            </div>
            <div className="modal-body">
              <p>检测到 <strong>{restartDialog.browserName}</strong> 正在运行，但未开启调试模式。</p>
              <p>要连接到用户浏览器，需要先关闭并重新启动 {restartDialog.browserName}（带调试端口）。</p>
              {restarting && <p className="modal-loading">正在重启 {restartDialog.browserName}...</p>}
            </div>
            <div className="modal-footer">
              <button className="btn btn-secondary" onClick={handleRestartCancel} disabled={restarting}>取消</button>
              <button className="btn btn-secondary" onClick={handleRestartIsolated} disabled={restarting}>使用隔离浏览器</button>
              <button className="btn btn-primary" onClick={handleRestartConfirm} disabled={restarting}>
                {restarting ? '重启中...' : '关闭并重启'}
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
          <span className="tab-icon">🎯</span> 执行
          {loading && <span className="tab-badge">运行中</span>}
        </div>
        <div className={`tab ${activeTab === 'agentmd' ? 'active' : ''}`} onClick={() => setActiveTab('agentmd')}>
          <span className="tab-icon">💬</span> 对话
        </div>
        <div className={`tab ${activeTab === 'log' ? 'active' : ''}`} onClick={() => setActiveTab('log')}>
          <span className="tab-icon">📋</span> 日志
          {pendingReview && <span className="tab-dot" />}
        </div>
        <div className="tab-spacer" />
        <div className={`tab ${activeTab === 'pipelines' ? 'active' : ''}`} onClick={() => setActiveTab('pipelines')}>
          <span className="tab-icon">📦</span> 管线
        </div>
        <div className={`tab ${activeTab === 'params' ? 'active' : ''}`} onClick={() => setActiveTab('params')}>
          <span className="tab-icon">⚙</span> 参数
        </div>
        <div className={`tab ${activeTab === 'settings' ? 'active' : ''}`} onClick={() => setActiveTab('settings')}>
          <span className="tab-icon">⚙</span> 设置
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
        <AgentMdTab
          pipelines={pipelines}
          activePreset={activePreset}
          onPresetChange={setActivePreset}
          chatMessages={chatMessages}
          onChatMessagesChange={setChatMessages}
          chatInput={chatInput}
          onChatInputChange={setChatInput}
          chatSending={chatSending}
          onChatSend={handleChatSend}
          preset={preset}
          agentMdEditor={agentMdEditor}
          onAgentMdEditorChange={setAgentMdEditor}
          onTabChange={setActiveTab}
          chatPendingDiffs={chatPendingDiffs}
          onChatDismiss={handleChatDismiss}
          onChatRollback={handleChatRollback}
          streamingMsg={streamingMsg}
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
        />
      </div>

      <StatusBar events={events} connected={connected} />
    </div>
  );
}
