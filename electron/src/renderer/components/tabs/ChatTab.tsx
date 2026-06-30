import React, { useState, useRef, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { ChatMessage, PendingEdit, TreeNode } from '../../types';
import * as api from '../../apiClient';
import MonacoYamlEditor from '../editor/MonacoYamlEditor';

interface ChatTabProps {
  treeNodes: TreeNode[];
  expandedNodes: Set<string>;
  onToggleExpand: (name: string) => void;
  sidebarCollapsed: boolean;
  onToggleSidebar: () => void;
  messages: ChatMessage[];
  setMessages: React.Dispatch<React.SetStateAction<ChatMessage[]>>;
  connected: boolean;
  activePreset: string;
  currentSessionId?: string;
  loadingSession?: boolean;
  onNewSession?: () => void;
  onSelectSession?: (sessionId: string) => void;
  onArchiveSession?: (sessionId: string) => void;
  pipelineEditor: string;
  onPipelineEditorChange: (text: string) => void;
  onRefreshPipeline: () => void;
  pendingEdit?: PendingEdit | null;
  onConfirmEdit?: (editId: string) => Promise<string | null>;
  onRevertEdit?: (editId: string) => Promise<string | null>;
  onDeletePipeline?: (name: string) => void;
  onSavePipeline?: () => Promise<void>;
  reversed?: boolean;
  theme?: string;
}

export default function ChatTab({
  treeNodes, expandedNodes, onToggleExpand,
  sidebarCollapsed, onToggleSidebar,
  messages, setMessages, connected,
  activePreset, currentSessionId, loadingSession,
  onNewSession, onSelectSession, onArchiveSession,
  pipelineEditor, onPipelineEditorChange, onRefreshPipeline,
  pendingEdit, onConfirmEdit, onRevertEdit,
  onDeletePipeline, onSavePipeline,
  reversed, theme,
}: ChatTabProps) {
  const { t } = useTranslation();
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [sessionStatus, setSessionStatus] = useState<string>('idle');
  const [diffError, setDiffError] = useState('');
  const scrollRef = useRef<HTMLDivElement>(null);
  const bodyRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const draggingRef = useRef(false);
  const [expandedThinks, setExpandedThinks] = useState<Set<number>>(new Set());
  const [expandedToolErrors, setExpandedToolErrors] = useState<Set<number>>(new Set());
  const cancelledRef = useRef(false);

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
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  const handleSplitMouseDown = (e: React.MouseEvent) => {
    e.preventDefault();
    draggingRef.current = true;
    const startX = e.clientX;
    const startRatio = splitRatio;
    const bodyWidth = bodyRef.current?.offsetWidth ?? 1;
    const sign = reversed ? -1 : 1;
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
    if (!text || sending) return;
    setInput('');
    resetTextarea();
    setSending(true);
    setSessionStatus('running');

    setMessages(prev => [...prev, { role: 'user', content: text }]);

    try {
      const pipelineName = activePreset || undefined;
      const result = await api.chat(text, pipelineName);
      if (result.ok) {
        onRefreshPipeline();
      } else {
        setMessages(prev => [...prev, { role: 'assistant', content: `Error: ${result.error ?? 'Unknown'}` }]);
      }
    } catch (e) {
      if (!cancelledRef.current) {
        setMessages(prev => [...prev, { role: 'assistant', content: `Error: ${String(e)}` }]);
      }
    } finally {
      cancelledRef.current = false;
      setSending(false);
      setSessionStatus('idle');
    }
  };

  const handleReset = async () => {
    try {
      const result = await api.chatReset();
      if (result.ok) {
        setMessages([]);
        setSessionStatus('idle');
      }
    } catch (e) {
      console.error('Chat reset failed:', e);
    }
  };

  const handleCancel = async () => {
    cancelledRef.current = true;
    try {
      await api.chatCancel();
    } catch (e) {
      console.error('Chat cancel failed:', e);
    }
    setSending(false);
    setSessionStatus('idle');
    setMessages(prev => [...prev, { role: 'system', content: t('chat.interrupted') }]);
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
        {onSavePipeline && (
          <button
            className="btn btn-small btn-primary"
            onClick={onSavePipeline}
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
                  const err = await onConfirmEdit?.(pendingEdit.edit_id);
                  if (err) setDiffError(err);
                }}
              >
                {t('chat.confirm')}
              </button>
              <button
                className="btn btn-small btn-secondary"
                onClick={async () => {
                  setDiffError('');
                  const err = await onRevertEdit?.(pendingEdit.edit_id);
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
        onChange={onPipelineEditorChange}
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

  const activeNode = treeNodes.find(n => n.name === activePreset);
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

        // Divider before pipeline section
        if (idx === 0 && hasPipelines && node.name === '__chat__') {
          parts.push(
            <div key="divider-label" className="tree-divider-label">Pipelines</div>,
            <div key="divider-line" className="tree-divider" />
          );
        }

        // Parent node header
        parts.push(
          <div key={node.name} className="tree-node">
            <div
              className={'tree-node-header' + (isActive ? ' active' : '')}
              onClick={() => onToggleExpand(node.name)}
            >
              <span className={'tree-node-arrow' + (isExpanded ? ' expanded' : '')}>▶</span>
              <span className="tree-node-icon">{node.isPipeline ? '📦' : '📁'}</span>
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
                  onClick={() => onSelectSession?.(s.session_id)}
                >
                  <span className={'tree-session-dot' + (currentSessionId === s.session_id ? ' active-dot' : '')}>
                    {currentSessionId === s.session_id ? '●' : '○'}
                  </span>
                  <span className="tree-session-label">{formatSessionLabel(s)}</span>
                  <span className="tree-session-count">{t('chat.sessionCount', { count: s.message_count })}</span>
                  <button
                    className="tree-session-archive"
                    title={t('chat.archiveSession', 'Archive')}
                    onClick={(e) => { e.stopPropagation(); onArchiveSession?.(s.session_id); }}
                  >
                    🗑
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
      <div className="chat-body" ref={bodyRef} style={{ flexDirection: reversed ? 'row-reverse' : 'row' }}>
        <div className={'chat-session-sidebar' + (sidebarCollapsed ? ' collapsed' : '')}>
          <div className="chat-session-header">
            <span className="chat-session-title">{t('chat.sessions', 'Sessions')}</span>
            <button
              className="btn-icon"
              onClick={onNewSession}
              disabled={loadingSession || messages.length === 0}
              title={t('chat.newSession', 'New Session')}
              style={{ width: 20, height: 20, border: '1px solid var(--border)', borderRadius: 3, background: 'transparent', color: 'var(--text-muted)', cursor: 'pointer', fontSize: 13, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, opacity: loadingSession || messages.length === 0 ? 0.35 : 1 }}
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
                onClick={onToggleSidebar}
                title={sidebarCollapsed ? t('chat.expandSidebar', 'Expand') : t('chat.collapseSidebar', 'Collapse')}
              >
                {sidebarCollapsed ? '▶' : '◀'}
              </button>
              <span className="chat-title">{activeNode?.label || t('chat.title')}</span>
              {activeNode && (
                <span className="tree-node-badge" style={{ fontSize: 10, color: 'var(--text-muted)' }}>
                  ({activeNode.sessions.length})
                </span>
              )}
              {sessionStatus && sessionStatus !== 'idle' && (
                <span className={`chat-status ${sessionStatus}`}>{sessionStatus}</span>
              )}
            </div>
            <div className="chat-header-actions">
              {activePreset && activePreset !== '__chat__' && (
                <button className="btn btn-small btn-danger" onClick={() => {
                  if (confirm(t('pipelineManager.deleteConfirm', { name: activeNode?.label || activePreset }))) {
                    onDeletePipeline?.(activePreset);
                  }
                }}>
                  🗑 {t('pipelineManager.delete')}
                </button>
              )}
              <button className="btn btn-small btn-secondary" onClick={handleReset}>
                {t('common.reset')}
              </button>
            </div>
          </div>
          <div className="chat-messages" ref={scrollRef}>
            {messages.length === 0 && (
              <div className="chat-empty">
                <span className="chat-empty-icon">💬</span>
                <p>{t('chat.startPrompt')}</p>
              </div>
            )}
            {messages.map((msg, i) => {
              if (msg.role === 'tool') {
                const statusClass = msg.toolOk === undefined ? '' : msg.toolOk ? 'ok' : 'err';
                const failed = msg.toolOk === false;
                const hasOutput = msg.content && msg.content !== 'Done' && msg.content !== 'Failed';
                return (
                  <div key={i} className={`chat-tool-inline${failed ? ' chat-tool-failed' : ''}`}>
                    <span className="chat-tool-inline-arrow">{failed ? '✗' : '↓'}</span>
                    <span className="chat-tool-inline-name">{msg.toolName}</span>
                    {msg.toolDuration !== undefined && (
                      <span className="chat-tool-inline-dur">{msg.toolDuration}ms</span>
                    )}
                    <span className={`chat-tool-inline-status ${statusClass}`}>
                      {msg.toolOk === undefined ? '...' : msg.toolOk ? '✓' : '✗'}
                    </span>
                    {hasOutput && (
                      <div className={`chat-tool-error-block ${expandedToolErrors.has(i) ? 'expanded' : ''}`}>
                        <div
                          className="chat-tool-error-header"
                          onClick={() => {
                            setExpandedToolErrors(prev => {
                              const next = new Set(prev);
                              if (next.has(i)) { next.delete(i); } else { next.add(i); }
                              return next;
                            });
                          }}
                        >
                          <span className="chat-tool-error-arrow">{expandedToolErrors.has(i) ? '▾' : '▸'}</span>
                          <span className="chat-tool-error-label">{failed ? t('chat.errorDetail') : t('chat.output')}</span>
                        </div>
                        {expandedToolErrors.has(i) && (
                          <div className="chat-tool-error-content">{msg.content}</div>
                        )}
                      </div>
                    )}
                  </div>
                );
              }
              if (msg.role === 'assistant') {
                return (
                  <div key={i} className="chat-msg assistant">
                    {msg.reasoning && (
                      <div className={`chat-think-block ${expandedThinks.has(i) ? 'expanded' : ''}`}>
                        <div
                          className="chat-think-header"
                          onClick={() => {
                            setExpandedThinks(prev => {
                              const next = new Set(prev);
                              if (next.has(i)) { next.delete(i); } else { next.add(i); }
                              return next;
                            });
                          }}
                        >
                          <span className="chat-think-arrow">{expandedThinks.has(i) ? '▾' : '▸'}</span>
                          <span className="chat-think-title">{t('chat.think')}</span>
                        </div>
                        {expandedThinks.has(i) && (
                          <div className="chat-think-content">{msg.reasoning}</div>
                        )}
                      </div>
                    )}
                    <div className="chat-markdown">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
                    </div>
                  </div>
                );
              }
              if (msg.role === 'user') {
                return (
                  <div key={i} className="chat-msg user">
                    <div className="chat-bubble user">
                      <div className="chat-markdown">
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
                      </div>
                    </div>
                  </div>
                );
              }
              return (
                <div key={i} className="chat-msg system">
                  <div className="chat-markdown">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
                  </div>
                </div>
              );
            })}
            {sending && (
              <div className="chat-msg assistant">
                <span className="chat-typing" />
              </div>
            )}
          </div>

          <div className="chat-input-area">
            <textarea
              ref={textareaRef}
              className="chat-input"
              value={input}
              onChange={e => { setInput(e.target.value); autoResize(); }}
              onKeyDown={handleKeyDown}
              placeholder={connected ? t('chat.placeholder') : t('chat.placeholderDisconnected')}
              disabled={!connected || sending}
              rows={2}
            />
            <button
              className={`btn chat-send-btn ${sending ? 'btn-danger' : 'btn-primary'}`}
              onClick={sending ? handleCancel : handleSend}
              disabled={!sending && (!input.trim() || !connected)}
            >
              {sending ? t('chat.stop') : t('chat.send')}
            </button>
          </div>
        </div>

        <div
          className="chat-split-handle"
          onMouseDown={handleSplitMouseDown}
        />

        <div className="chat-right" style={{ flex: 1 }}>
          {editorPanel}
        </div>
      </div>
    </div>
  );
}
