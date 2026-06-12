import React, { useState, useRef, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import type { ChatMessage, PipelineMeta, PendingEdit } from '../../types';
import MonacoYamlEditor from '../editor/MonacoYamlEditor';

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
  reversed?: boolean;
  theme?: string;
}

export default function ChatTab({
  messages, setMessages, connected,
  pipelines, activePreset, onPresetChange,
  pipelineEditor, onPipelineEditorChange, onRefreshPipeline,
  pendingEdit, onConfirmEdit, onRevertEdit,
  reversed, theme,
}: ChatTabProps) {
  const { t } = useTranslation();
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [sessionStatus, setSessionStatus] = useState<string>('idle');
  const [editorSaved, setEditorSaved] = useState(false);
  const [diffError, setDiffError] = useState('');
  const scrollRef = useRef<HTMLDivElement>(null);
  const bodyRef = useRef<HTMLDivElement>(null);
  const draggingRef = useRef(false);

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

  const handleSend = async () => {
    const text = input.trim();
    if (!text || sending) return;
    setInput('');
    setSending(true);

    setMessages([...messages, { role: 'user', content: text }]);

    try {
      const result = await window.electronAPI.chat(text);
      if (result.ok) {
        const resp = result.response;
        if (resp) {
          setMessages(prev => [...prev, { role: 'assistant', content: resp }]);
        }
        setSessionStatus(result.status || 'completed');
        onRefreshPipeline();
      } else {
        setMessages(prev => [...prev, { role: 'assistant', content: `Error: ${result.error ?? 'Unknown'}` }]);
      }
    } catch (e) {
      setMessages(prev => [...prev, { role: 'assistant', content: `Error: ${String(e)}` }]);
    } finally {
      setSending(false);
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
    try {
      await window.electronAPI.chatCancel();
    } catch (e) {
      console.error('Chat cancel failed:', e);
    }
  };

  const handleSavePipeline = async () => {
    try {
      await window.electronAPI.savePreset(activePreset, pipelineEditor);
      setEditorSaved(true);
      setTimeout(() => setEditorSaved(false), 2000);
    } catch (e) {
      console.error('Save pipeline failed:', e);
    }
  };

  const handleCompilePreset = async () => {
    try {
      const result = await window.electronAPI.compilePreset(activePreset);
      if (result.ok) {
        setMessages(prev => [...prev, {
          role: 'system',
          content: `Preset saved: ${activePreset}`,
        }]);
        onRefreshPipeline();
      }
    } catch (e) {
      console.error('Compile preset failed:', e);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const editorPanel = (
    <div className="chat-pipeline-editor">
      {pendingEdit ? (
        <>
          <div className="chat-diff-bar">
            <span className="chat-diff-explanation">
              {pendingEdit.original === pendingEdit.modified
                ? (pendingEdit.explanation || 'No changes detected — content is identical')
                : (pendingEdit.explanation || 'AI suggested changes to the pipeline')}
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
                {t('chat.confirm') || 'Confirm'}
              </button>
              <button
                className="btn btn-small btn-secondary"
                onClick={async () => {
                  setDiffError('');
                  const err = await onRevertEdit?.(pendingEdit.edit_id);
                  if (err) setDiffError(err);
                }}
              >
                {t('chat.revert') || 'Revert'}
              </button>
            </div>
          </div>
          {diffError && (
            <div className="chat-diff-error">{diffError}</div>
          )}
          <MonacoYamlEditor
            value={pipelineEditor}
            original={pendingEdit.original}
            modified={pendingEdit.modified}
            onChange={onPipelineEditorChange}
            theme={theme}
          />
        </>
      ) : (
        <>
          <div className="chat-pipeline-toolbar">
            <button
              className="btn btn-small btn-secondary"
              onClick={handleCompilePreset}
              disabled={!activePreset || sending}
            >
              {t('chat.compilePreset')}
            </button>
            <button
              className={`btn btn-small ${editorSaved ? 'btn-primary' : 'btn-secondary'}`}
              onClick={handleSavePipeline}
              disabled={!activePreset}
            >
              {editorSaved ? '✓ Saved' : t('chat.save')}
            </button>
          </div>
          <MonacoYamlEditor
            value={pipelineEditor}
            onChange={onPipelineEditorChange}
            theme={theme}
          />
        </>
      )}
    </div>
  );

  return (
    <div className="chat-layout">
      <div className="chat-body" ref={bodyRef} style={{ flexDirection: reversed ? 'row-reverse' : 'row' }}>
        <div className="chat-left" style={{ width: `${splitRatio}%`, flex: 'none' }}>
          <div className="chat-header">
            <div className="chat-header-left">
              <span className="chat-title">Chat</span>
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
              <button className="btn btn-small btn-secondary" onClick={handleCancel} disabled={sessionStatus !== 'running'}>
                {t('common.cancel')}
              </button>
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
            {messages.map((msg, i) => (
              <div key={i} className={`chat-msg ${msg.role}`}>
                {msg.role !== 'user' && (
                  <span className={`chat-avatar ${msg.role}`}>
                    {msg.role === 'assistant' ? 'A' : msg.role === 'tool' ? '🔧' : '⚡'}
                  </span>
                )}
                <div className={`chat-bubble ${msg.role}`}>
                  {msg.role === 'tool' && msg.toolName && (
                    <div className="chat-tool-header">
                      <span className={`chat-tool-indicator ${msg.toolOk ? 'ok' : 'err'}`}>
                        {msg.toolOk ? '✓' : '✗'}
                      </span>
                      <span className="chat-tool-name">{msg.toolName}</span>
                      {msg.toolDuration !== undefined && (
                        <span className="chat-tool-duration">{msg.toolDuration}ms</span>
                      )}
                    </div>
                  )}
                  <div className="chat-bubble-text">{msg.content}</div>
                </div>
                {msg.role === 'user' && <span className="chat-avatar user">U</span>}
              </div>
            ))}
            {sending && (
              <div className="chat-msg assistant">
                <span className="chat-avatar assistant">A</span>
                <div className="chat-bubble assistant">
                  <span className="chat-typing">...</span>
                </div>
              </div>
            )}
          </div>

          <div className="chat-input-area">
            <textarea
              className="chat-input"
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={t('chat.placeholder')}
              disabled={!connected || sending}
              rows={2}
            />
            <button
              className="btn btn-primary chat-send-btn"
              onClick={handleSend}
              disabled={!input.trim() || sending || !connected}
            >
              {sending ? '...' : t('chat.send')}
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
