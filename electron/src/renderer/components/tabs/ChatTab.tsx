import React, { useState, useRef, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { ChatMessage, PipelineMeta, PendingEdit } from '../../types';
import MonacoYamlEditor from '../editor/MonacoYamlEditor';

interface SessionMeta {
  session_id: string;
  display_name?: string | null;
  created_at: string;
  message_count: number;
  status: string;
}

interface ChatTabProps {
  messages: ChatMessage[];
  setMessages: React.Dispatch<React.SetStateAction<ChatMessage[]>>;
  connected: boolean;
  pipelines: PipelineMeta[];
  activePreset: string;
  onPresetChange: (name: string) => void;
  pipelineEditor: string;
  onPipelineEditorChange: (text: string) => void;
  onRefreshPipeline: () => void;
  pendingEdit?: PendingEdit | null;
  onConfirmEdit?: (editId: string) => Promise<string | null>;
  onRevertEdit?: (editId: string) => Promise<string | null>;
  onDeletePipeline?: (name: string) => void;
  reversed?: boolean;
  theme?: string;
  sessions?: SessionMeta[];
  currentSessionId?: string;
  loadingSession?: boolean;
  onNewSession?: () => void;
  onSelectSession?: (sessionId: string) => void;
}

export default function ChatTab({
  messages, setMessages, connected,
  pipelines, activePreset, onPresetChange,
  pipelineEditor, onPipelineEditorChange, onRefreshPipeline,
  pendingEdit, onConfirmEdit, onRevertEdit,
  onDeletePipeline,
  reversed, theme,
  sessions, currentSessionId, loadingSession, onNewSession, onSelectSession,
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
      const result = await window.electronAPI.chat(text, pipelineName);
      if (result.ok) {
        const resp = result.response;
        if (resp) {
          setMessages(prev => [...prev, { role: 'assistant', content: resp }]);
        }
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
      const result = await window.electronAPI.chatReset();
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
      await window.electronAPI.chatCancel();
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

  const formatSessionLabel = (s: SessionMeta): string => {
    try {
      const datePart = s.created_at.slice(0, 16).replace('T', ' ');
      return `${datePart} (${s.message_count})`;
    } catch {
      return s.session_id.slice(-8);
    }
  };

  return (
    <div className="chat-layout">
      <div className="chat-body" ref={bodyRef} style={{ flexDirection: reversed ? 'row-reverse' : 'row' }}>
        <div className="chat-session-sidebar">
          <div className="chat-session-header">
            <span className="chat-session-title">{t('chat.sessions', 'Sessions')}</span>
            <button
              className="btn btn-small btn-primary"
              onClick={onNewSession}
              disabled={loadingSession}
              title={t('chat.newSession', 'New Session')}
            >
              +
            </button>
          </div>
          <div className="chat-session-list">
            {(!sessions || sessions.length === 0) && (
              <div className="chat-session-empty">{t('chat.noSessions', 'No sessions')}</div>
            )}
            {sessions?.map(s => (
              <div
                key={s.session_id}
                className={`chat-session-item ${currentSessionId === s.session_id ? 'active' : ''}`}
                onClick={() => onSelectSession?.(s.session_id)}
              >
                <span className="chat-session-label">{formatSessionLabel(s)}</span>
              </div>
            ))}
          </div>
        </div>
        <div className="chat-left" style={{ width: `${splitRatio}%`, flex: 'none' }}>
          <div className="chat-header">
            <div className="chat-header-left">
              <span className="chat-title">{t('chat.title')}</span>
              <select
                className="select"
                value={activePreset}
                onChange={e => onPresetChange(e.target.value)}
              >
                {pipelines.length === 0 && (
                  <option value="">{t('preset.noPipelines')}</option>
                )}
                {pipelines.map(p => (
                  <option key={p.name} value={p.name}>{p.title || p.name}</option>
                ))}
              </select>
              {sessionStatus && sessionStatus !== 'idle' && (
                <span className={`chat-status ${sessionStatus}`}>{sessionStatus}</span>
              )}
            </div>
            <div className="chat-header-actions">
              <button className="btn btn-small btn-danger" onClick={() => {
                if (confirm(t('pipelineManager.deleteConfirm', { name: activePreset }))) {
                  onDeletePipeline?.(activePreset);
                }
              }}>🗑 {t('pipelineManager.delete')}</button>
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
                    {failed && msg.content && msg.content !== 'Failed' && (
                      <div className="chat-tool-error">{msg.content}</div>
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
                <span className="chat-typing">...</span>
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
