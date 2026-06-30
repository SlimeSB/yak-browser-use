import React, { useState, useRef, useEffect, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { useChatStore } from '../../stores/chatStore';
import type { ChatMessage } from '../../types';
import { useConnectionStore } from '../../stores/connectionStore';
import { usePipelineStore } from '../../stores/pipelineStore';
import { useUiStore } from '../../stores/uiStore';
import MonacoYamlEditor from '../editor/MonacoYamlEditor';

export default function ChatTab() {
  const { t } = useTranslation();
  const messages = useChatStore(s => s.chatMessages);
  const connected = useConnectionStore(s => s.connected);
  const currentSessionId = useChatStore(s => s.currentSessionId);
  const loadingSession = useChatStore(s => s.loadingSession);
  const pendingEdit = useChatStore(s => s.activePendingEdit);
  const treeNodes = useChatStore(s => s.selectTreeNodes);
  const expandedNodes = useChatStore(s => s.expandedNodes);
  const activePreset = usePipelineStore(s => s.activePreset);
  const pipelineEditor = usePipelineStore(s => s.pipelineEditor);
  const send = useChatStore(s => s.send);
  const cancelChat = useChatStore(s => s.cancelChat);
  const resetChat = useChatStore(s => s.resetChat);
  const newSession = useChatStore(s => s.newSession);
  const loadSessions = useChatStore(s => s.loadSessions);
  const archiveSession = useChatStore(s => s.archiveSession);
  const selectSession = useChatStore(s => s.selectSession);
  const toggleExpand = useChatStore(s => s.toggleExpand);
  const confirmEdit = useChatStore(s => s.confirmEdit);
  const revertEdit = useChatStore(s => s.revertEdit);
  const setPipelineEditor = usePipelineStore(s => s.setPipelineEditor);
  const deletePipeline = usePipelineStore(s => s.deletePipeline);
  const savePipeline = usePipelineStore(s => s.savePipeline);
  const sidebarCollapsed = useUiStore(s => s.sidebarCollapsed);
  const setSidebarCollapsed = useUiStore(s => s.setSidebarCollapsed);
  const chatLayoutReversed = useUiStore(s => s.chatLayoutReversed);
  const theme = useUiStore(s => s.theme);

  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const sendingRef = useRef(false);
  const [sessionStatus, setSessionStatus] = useState<string>('idle');
  const [diffError, setDiffError] = useState('');
  const scrollRef = useRef<HTMLDivElement>(null);
  const bodyRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const draggingRef = useRef(false);
  const [expandedThinks, setExpandedThinks] = useState<Set<string>>(new Set());
  const [expandedToolCalls, setExpandedToolCalls] = useState<Set<string>>(new Set());
  const cancelledRef = useRef(false);
  const activePresetRef = useRef(activePreset);
  const connectedRef = useRef(connected);

  useEffect(() => { activePresetRef.current = activePreset; }, [activePreset]);
  useEffect(() => { connectedRef.current = connected; }, [connected]);

  useEffect(() => {
    loadSessions(activePreset);
  }, []);

  const mergedMessages = useMemo(() => {
    const result: (ChatMessage & { toolCalls?: ChatMessage[] })[] = [];
    for (let i = 0; i < messages.length; i++) {
      const msg = messages[i];
      if (msg.role === 'tool') continue;
      if (msg.role === 'assistant') {
        const tools: ChatMessage[] = [];
        while (i + 1 < messages.length && messages[i + 1].role === 'tool') {
          tools.push(messages[i + 1]);
          i++;
        }
        if (!msg.content && !msg.reasoning && tools.length > 0 && result.length > 0) {
          const prev = result[result.length - 1];
          if (prev.role === 'assistant') {
            prev.toolCalls = [...(prev.toolCalls || []), ...tools];
            continue;
          }
        }
        result.push({ ...msg, toolCalls: tools.length > 0 ? tools : undefined });
      } else {
        result.push(msg);
      }
    }
    return result;
  }, [messages]);

  const [splitRatio, setSplitRatio] = useState(() => {
    try {
      const saved = localStorage.getItem('chat-split-ratio');
      const n = parseFloat(saved || '');
      return (n >= 20 && n <= 80) ? n : 50;
    } catch { return 50; }
  });

  useEffect(() => {
    try { localStorage.setItem('chat-split-ratio', String(splitRatio)); } catch { /* ok */ }
  }, [splitRatio]);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const isNearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 100;
    if (isNearBottom) {
      el.scrollTop = el.scrollHeight;
    }
  }, [messages]);

  const handleSplitMouseDown = (e: React.MouseEvent) => {
    e.preventDefault();
    draggingRef.current = true;
    const startX = e.clientX;
    const startRatio = splitRatio;
    const bodyWidth = bodyRef.current?.offsetWidth ?? 1;
    const sign = chatLayoutReversed ? -1 : 1;
    document.body.style.userSelect = 'none';

    const onMove = (ev: MouseEvent) => {
      if (!draggingRef.current) return;
      const dx = (ev.clientX - startX) * sign;
      const newRatio = Math.min(80, Math.max(20, startRatio + (dx / bodyWidth) * 100));
      setSplitRatio(newRatio);
    };
    const onUp = () => {
      draggingRef.current = false;
      document.body.style.userSelect = '';
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);
    };
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
  };

  useEffect(() => {
    return () => {
      draggingRef.current = false;
      document.body.style.userSelect = '';
    };
  }, []);

  const autoResize = () => {
    const el = textareaRef.current;
    if (el) {
      el.style.height = 'auto';
      el.style.height = Math.min(el.scrollHeight, 300) + 'px';
    }
  };

  const resetTextarea = () => {
    const el = textareaRef.current;
    if (el) {
      el.style.height = '';
    }
  };

  const handleSend = async () => {
    const text = input.trim();
    if (!text || sendingRef.current) return;
    setInput('');
    resetTextarea();
    sendingRef.current = true;
    setSending(true);
    setSessionStatus('running');

    await send(text);

    cancelledRef.current = false;
    sendingRef.current = false;
    setSending(false);
    setSessionStatus('idle');
  };

  const handleReset = async () => {
    await resetChat();
    setSessionStatus('idle');
  };

  const handleCancel = async () => {
    cancelledRef.current = true;
    await cancelChat();
    sendingRef.current = false;
    setSending(false);
    setSessionStatus('idle');
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const editorPanel = (
    <div className="chat-pipeline-editor">
      <div className="chat-editor-toolbar">
        {activePreset !== '__chat__' && (
          <button
            className="btn btn-small btn-primary"
            onClick={savePipeline}
            title={t('chat.savePipeline', 'Save pipeline')}
          >
            {t('chat.save', 'Save')}
          </button>
        )}
      </div>
      {pendingEdit && (
        <>
          <div className="chat-diff-bar">
            <span className="chat-diff-explanation">
              {pendingEdit.original === pendingEdit.modified
                ? (pendingEdit.explanation || t('chat.noChanges'))
                : (pendingEdit.explanation || t('chat.suggestedChanges'))}
            </span>
            <div className="chat-diff-actions">
              <button
                className="btn btn-small btn-primary"
                onClick={async () => {
                  setDiffError('');
                  const err = await confirmEdit(pendingEdit.edit_id);
                  if (err) setDiffError(err);
                }}
              >
                {t('chat.confirm')}
              </button>
              <button
                className="btn btn-small btn-secondary"
                onClick={async () => {
                  setDiffError('');
                  const err = await revertEdit(pendingEdit.edit_id);
                  if (err) setDiffError(err);
                }}
              >
                {t('chat.revert')}
              </button>
            </div>
          </div>
          {diffError && (
            <div className="chat-diff-error">{diffError}</div>
          )}
        </>
      )}
      <MonacoYamlEditor
        value={pipelineEditor}
        original={pendingEdit?.original}
        modified={pendingEdit?.modified}
        onChange={setPipelineEditor}
        theme={theme}
      />
    </div>
  );

  const formatSessionLabel = (s: { session_id: string; created_at: string; message_count: number }): string => {
    try {
      const datePart = s.created_at.slice(0, 16).replace('T', ' ');
      return `${datePart} (${s.message_count})`;
    } catch {
      return s.session_id.slice(-8);
    }
  };

  const hasPipelines = treeNodes.some(n => n.isPipeline);

  const renderTree = () => (
    <div className="chat-session-list">
      {treeNodes.length === 0 && (
        <div className="chat-session-empty">{t('chat.noSessions', 'No sessions')}</div>
      )}
      {treeNodes.map((node, idx) => {
        const isExpanded = expandedNodes.has(node.name);
        const isActive = activePreset === node.name;

        const parts: React.ReactNode[] = [];

        if (idx === 0 && hasPipelines && node.name === '__chat__') {
          parts.push(
            <div key="divider-label" className="tree-divider-label">Pipelines</div>,
            <div key="divider-line" className="tree-divider" />
          );
        }

        parts.push(
          <div key={node.name} className="tree-node">
            <div
              className={'tree-node-header' + (isActive ? ' active' : '')}
              onClick={() => toggleExpand(node.name)}
            >
              <span className={'tree-node-arrow' + (isExpanded ? ' expanded' : '')}>{'>'}</span>
              <span className="tree-node-label">{node.label}</span>
              <span className="tree-node-badge">({node.sessions.length})</span>
            </div>
            <div className={'tree-children' + (isExpanded ? '' : ' collapsed')}
              style={{ maxHeight: isExpanded ? node.sessions.length * 28 + 8 + 'px' : 0 }}
            >
              {node.sessions.map(s => (
                <div
                  key={s.session_id}
                  className={'tree-session' + (currentSessionId === s.session_id ? ' active' : '')}
                  onClick={async () => {
                    if (node.name !== activePreset) await toggleExpand(node.name);
                    selectSession(s.session_id);
                  }}
                >
                  <span className={'tree-session-dot' + (currentSessionId === s.session_id ? ' active-dot' : '')}>
                    {currentSessionId === s.session_id ? '●' : '○'}
                  </span>
                  <span className="tree-session-label">{formatSessionLabel(s)}</span>
                  <span className="tree-session-count">{t('chat.sessionCount', { count: s.message_count })}</span>
                  <button
                    className="tree-session-archive"
                    title={t('chat.archiveSession', 'Archive')}
                    onClick={(e) => { e.stopPropagation(); archiveSession(s.session_id); }}
                  >
                    ✕
                  </button>
                </div>
              ))}
            </div>
          </div>
        );

        return parts;
      })}
    </div>
  );

  return (
    <div className="chat-layout">
      <div className="chat-body" ref={bodyRef} style={{ flexDirection: chatLayoutReversed ? 'row-reverse' : 'row' }}>
        <div className={'chat-session-sidebar' + (sidebarCollapsed ? ' collapsed' : '')}>
          <div className="chat-session-header">
            <span className="chat-session-title">{t('chat.sessions', 'Sessions')}</span>
            <button
              className="btn-icon"
              onClick={newSession}
              disabled={loadingSession || messages.length === 0}
              title={t('chat.newSession', 'New Session')}
              style={{ width: 22, height: 22, border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', background: 'transparent', color: 'var(--text-muted)', cursor: 'pointer', fontSize: 'var(--fs-base)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, opacity: loadingSession || messages.length === 0 ? 0.35 : 1 }}
            >
              +
            </button>
          </div>
          {renderTree()}
        </div>

        <div className="chat-left" style={{ width: `${splitRatio}%`, flex: 'none' }}>
          <div className="chat-header">
            <div className="chat-header-left">
              <button
                className="btn-collapse"
                onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
                title={sidebarCollapsed ? t('chat.expandSidebar', 'Expand') : t('chat.collapseSidebar', 'Collapse')}
              >
                {sidebarCollapsed ? '▶' : '◀'}
              </button>
              {activePreset !== '__chat__' && (
                <span className="chat-title">{treeNodes.find(n => n.name === activePreset)?.label || t('chat.title')}</span>
              )}
            </div>
            <div className="chat-header-right">
              <button className="btn btn-small btn-secondary" onClick={handleReset} title={t('common.reset')}>
                {t('common.reset')}
              </button>
            </div>
          </div>

          <div className="chat-messages" ref={scrollRef}>
            {messages.length === 0 && (
              <div className="chat-empty">
                <div className="chat-empty-icon">💬</div>
                <p>{t('chat.startPrompt')}</p>
                <span className="chat-empty-hint">{t('chat.placeholder')}</span>
              </div>
            )}
            {mergedMessages.map((msg, i) => {
              const thinkKey = `${msg.id! || i}_think`;
              return (
                <div key={msg.id || i} className={`chat-message ${msg.role}`}>
                  {msg.role === 'user' && <div className="chat-user-bubble"><pre>{msg.content}</pre></div>}
                  {msg.role === 'assistant' && (
                    <>
                      {msg.reasoning && (
                        <div className="chat-think">
                          <span className={`chat-think-toggle${expandedThinks.has(thinkKey) ? ' expanded' : ''}`}
                            onClick={() => setExpandedThinks(prev => {
                              const next = new Set(prev);
                              if (next.has(thinkKey)) next.delete(thinkKey); else next.add(thinkKey);
                              return next;
                            })}
                          >
                            <span className="arrow">▶</span>
                            <span className="chat-think-title">{t('chat.think')}</span>
                          </span>
                          {expandedThinks.has(thinkKey) && (
                            <pre className="chat-think-body">{msg.reasoning}</pre>
                          )}
                        </div>
                      )}
                      {msg.content && (
                        <div className="chat-agent-content"><ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown></div>
                      )}
                      {((msg as any).toolCalls?.length ?? 0) > 0 && (
                        <div className="tool-chips">
                          {(msg as any).toolCalls.map((tc: ChatMessage, j: number) => {
                            const isRunning = tc.toolOk === undefined;
                            const isOk = tc.toolOk === true;
                            const isErr = tc.toolOk === false;
                            const toolKey = tc.toolCallId || `${i}-${j}`;
                            const isExpanded = expandedToolCalls.has(toolKey);
                            return (
                              <div key={toolKey} className="tool-chip-wrapper">
                                <div
                                  className={`tool-chip ${isRunning ? 'status-running' : isOk ? 'status-ok' : 'status-err'}${isExpanded ? ' expanded' : ''}`}
                                  onClick={() => setExpandedToolCalls(prev => {
                                    const next = new Set(prev);
                                    if (next.has(toolKey)) next.delete(toolKey); else next.add(toolKey);
                                    return next;
                                  })}
                                >
                                  <span className="icon">{isRunning ? '◌' : isOk ? '✓' : '✗'}</span>
                                  <span className="name">{tc.toolName || t('chat.title')}</span>
                                  {tc.toolDuration !== undefined && (
                                    <><span className="sep">·</span><span className="duration">{tc.toolDuration}ms</span></>
                                  )}
                                </div>
                                {isExpanded && tc.content && (
                                  <pre className="tool-chip-body">{tc.content}</pre>
                                )}
                              </div>
                            );
                          })}
                        </div>
                      )}
                    </>
                  )}
                  {msg.role === 'system' && (
                    <div className="chat-system-msg"><pre>{msg.content}</pre></div>
                  )}
                </div>
              );
            })}
          </div>

          <div className="chat-input-area">
            <textarea
              ref={textareaRef}
              className="chat-input"
              value={input}
              onChange={e => { setInput(e.target.value); autoResize(); }}
              onKeyDown={handleKeyDown}
              placeholder={connected ? t('chat.placeholder') : t('chat.placeholderDisconnected')}
              rows={1}
              disabled={!connected || sending}
            />
            <button
              className={`btn btn-sm ${sending ? 'btn-danger' : 'btn-primary'}`}
              onClick={sending ? handleCancel : handleSend}
              disabled={(!input.trim() && !sending) || !connected}
              style={{ flexShrink: 0 }}
            >
              {sending ? t('chat.stop') : t('chat.send')}
            </button>
          </div>
        </div>

        <div className="chat-divider" onMouseDown={handleSplitMouseDown} />

        {editorPanel}
      </div>
    </div>
  );
}
