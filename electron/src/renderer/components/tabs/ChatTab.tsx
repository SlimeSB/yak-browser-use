import React, { useState, useRef, useEffect, useMemo, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { useChatStore } from '../../stores/chatStore';
import type { ChatMessage, TreeNode } from '../../types';
import { usePipelineStore } from '../../stores/pipelineStore';
import { useUiStore } from '../../stores/uiStore';
import MonacoYamlEditor from '../editor/MonacoYamlEditor';
import { readStorage, writeStorage } from '../../utils/storage';

// ── Tree sidebar ─────────────────────────────────────────────

function SessionTree() {
  const { t } = useTranslation();
  const pipelines = usePipelineStore(s => s.pipelines);
  const chatSessions = useChatStore(s => s.chatSessions);
  const pipelineSessions = useChatStore(s => s.pipelineSessions);
  const expandedNodes = useChatStore(s => s.expandedNodes);
  const currentSessionId = useChatStore(s => s.currentSessionId);
  const activePreset = usePipelineStore(s => s.activePreset);
  const toggleExpand = useChatStore(s => s.toggleExpand);
  const selectSession = useChatStore(s => s.selectSession);
  const archiveSession = useChatStore(s => s.archiveSession);

  const treeNodes = useMemo((): TreeNode[] => {
    const nodes: TreeNode[] = [
      { name: '__chat__', label: 'No Workspace', isPipeline: false, sessions: chatSessions },
    ];
    for (const p of pipelines) {
      nodes.push({
        name: p.name,
        label: p.title || p.name,
        isPipeline: true,
        sessions: pipelineSessions[p.name] ?? [],
      });
    }
    return nodes;
  }, [pipelines, chatSessions, pipelineSessions]);

  const hasPipelines = treeNodes.some(n => n.isPipeline);

  const formatLabel = (s: { session_id: string; created_at: string; message_count: number }) => {
    try {
      return `${s.created_at.slice(0, 16).replace('T', ' ')} (${s.message_count})`;
    } catch {
      return s.session_id.slice(-8);
    }
  };

  return (
    <div className="chat-session-list">
      {treeNodes.map((node, idx) => {
        const isExpanded = expandedNodes.has(node.name);
        const isActive = activePreset === node.name;
        const parts: React.ReactNode[] = [];

        if (idx === 0 && hasPipelines && node.name === '__chat__') {
          parts.push(
            <div key="divider-label" className="tree-divider-label">Pipelines</div>,
            <div key="divider-line" className="tree-divider" />,
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
            <div
              className={'tree-children' + (isExpanded ? '' : ' collapsed')}
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
                  <span className="tree-session-label">{formatLabel(s)}</span>
                  <span className="tree-session-count">{t('chat.sessionCount', { count: s.message_count })}</span>
                  <button
                    className="tree-session-archive"
                    title={t('chat.archiveSession', 'Archive')}
                    onClick={(e) => { e.stopPropagation(); archiveSession(s.session_id); }}
                  >✕</button>
                </div>
              ))}
            </div>
          </div>,
        );

        return parts;
      })}
    </div>
  );
}

// ── Editor panel ─────────────────────────────────────────────

function EditorPanel() {
  const { t } = useTranslation();
  const pendingEdit = useChatStore(s => s.activePendingEdit);
  const activePreset = usePipelineStore(s => s.activePreset);
  const pipelineEditor = usePipelineStore(s => s.pipelineEditor);
  const theme = useUiStore(s => s.theme);
  const confirmEdit = useChatStore(s => s.confirmEdit);
  const revertEdit = useChatStore(s => s.revertEdit);
  const setPipelineEditor = usePipelineStore(s => s.setPipelineEditor);
  const savePipeline = usePipelineStore(s => s.savePipeline);
  const [diffError, setDiffError] = useState('');

  return (
    <div className="chat-pipeline-editor">
      <div className="chat-editor-toolbar">
        {activePreset !== '__chat__' && (
          <button className="btn btn-small btn-primary" onClick={savePipeline} title={t('chat.savePipeline', 'Save pipeline')}>
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
              <button className="btn btn-small btn-primary" onClick={async () => {
                setDiffError('');
                const err = await confirmEdit(pendingEdit.edit_id);
                if (err) setDiffError(err);
              }}>{t('chat.confirm')}</button>
              <button className="btn btn-small btn-secondary" onClick={async () => {
                setDiffError('');
                const err = await revertEdit(pendingEdit.edit_id);
                if (err) setDiffError(err);
              }}>{t('chat.revert')}</button>
            </div>
          </div>
          {diffError && <div className="chat-diff-error">{diffError}</div>}
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
}

// ── Tool chip ────────────────────────────────────────────────

interface ToolChipProps {
  tc: ChatMessage;
}

function ToolChip({ tc }: ToolChipProps) {
  const [expanded, setExpanded] = useState(false);
  const isRunning = tc.toolOk === undefined;
  const isOk = tc.toolOk === true;
  const isErr = tc.toolOk === false;

  return (
    <div className="tool-chip-wrapper">
      <div
        className={`tool-chip ${isRunning ? 'status-running' : isOk ? 'status-ok' : 'status-err'}${expanded ? ' expanded' : ''}`}
        onClick={() => setExpanded(v => !v)}
      >
        <span className="icon">{isRunning ? '◌' : isOk ? '✓' : '✗'}</span>
        <span className="name">{tc.toolName || 'tool'}</span>
        {tc.toolDuration !== undefined && (
          <><span className="sep">·</span><span className="duration">{tc.toolDuration}ms</span></>
        )}
      </div>
      {expanded && tc.content && <pre className="tool-chip-body">{tc.content}</pre>}
    </div>
  );
}

// ── Message bubble ───────────────────────────────────────────

interface MessageBubbleProps {
  msg: ChatMessage;
  toolCalls?: ChatMessage[];
}

function MessageBubble({ msg, toolCalls }: MessageBubbleProps) {
  const { t } = useTranslation();
  const [thinkExpanded, setThinkExpanded] = useState(false);

  if (msg.role === 'user') {
    return <div className="chat-user-bubble"><pre>{msg.content}</pre></div>;
  }

  if (msg.role === 'system') {
    return <div className="chat-system-msg"><pre>{msg.content}</pre></div>;
  }

  // assistant
  return (
    <>
      {msg.reasoning && (
        <div className="chat-think">
          <span
            className={`chat-think-toggle${thinkExpanded ? ' expanded' : ''}`}
            onClick={() => setThinkExpanded(v => !v)}
          >
            <span className="arrow">▶</span>
            <span className="chat-think-title">{t('chat.think')}</span>
          </span>
          {thinkExpanded && <pre className="chat-think-body">{msg.reasoning}</pre>}
        </div>
      )}
      {msg.content && (
        <div className="chat-agent-content"><ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown></div>
      )}
      {(toolCalls?.length ?? 0) > 0 && (
        <div className="tool-chips">
          {toolCalls!.map((tc, j) => (
            <ToolChip key={tc.toolCallId || `${msg.id}-${j}`} tc={tc} />
          ))}
        </div>
      )}
    </>
  );
}

// ── Main component ───────────────────────────────────────────

export default function ChatTab() {
  const { t } = useTranslation();
  const messages = useChatStore(s => s.chatMessages);
  const currentSessionId = useChatStore(s => s.currentSessionId);
  const pendingEdit = useChatStore(s => s.activePendingEdit);
  const pipelines = usePipelineStore(s => s.pipelines);
  const activePreset = usePipelineStore(s => s.activePreset);
  const loadingSession = useChatStore(s => s.loadingSession);

  const send = useChatStore(s => s.send);
  const cancelChat = useChatStore(s => s.cancelChat);
  const resetChat = useChatStore(s => s.resetChat);
  const newSession = useChatStore(s => s.newSession);
  const loadSessions = useChatStore(s => s.loadSessions);
  const sidebarCollapsed = useUiStore(s => s.sidebarCollapsed);
  const setSidebarCollapsed = useUiStore(s => s.setSidebarCollapsed);
  const chatLayoutReversed = useUiStore(s => s.chatLayoutReversed);

  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const sendingRef = useRef(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const cancelledRef = useRef(false);

  // Auto-load sessions on mount
  useEffect(() => { loadSessions(activePreset); }, []);

  // Merge assistant messages with their tool calls
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
            prev.toolCalls = [...(prev.toolCalls ?? []), ...tools];
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

  // Auto-scroll
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    if (el.scrollHeight - el.scrollTop - el.clientHeight < 100) {
      el.scrollTop = el.scrollHeight;
    }
  }, [messages]);

  // Split ratio
  const [splitRatio, setSplitRatio] = useState(() => {
    const n = readStorage('chat-split-ratio', 0);
    return (n >= 20 && n <= 80) ? n : 50;
  });

  useEffect(() => { writeStorage('chat-split-ratio', splitRatio); }, [splitRatio]);

  // Handlers
  const autoResize = () => {
    const el = textareaRef.current;
    if (el) { el.style.height = 'auto'; el.style.height = Math.min(el.scrollHeight, 300) + 'px'; }
  };

  const handleSend = async () => {
    const text = input.trim();
    if (!text || sendingRef.current) return;
    setInput('');
    textareaRef.current!.style.height = '';
    sendingRef.current = true;
    setSending(true);
    await send(text);
    cancelledRef.current = false;
    sendingRef.current = false;
    setSending(false);
  };

  const handleCancel = async () => {
    cancelledRef.current = true;
    await cancelChat();
    sendingRef.current = false;
    setSending(false);
  };

  // Divider drag-to-resize
  const bodyRef = useRef<HTMLDivElement>(null);
  const draggingRef = useRef(false);

  const handleDividerMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    draggingRef.current = true;
    const startX = e.clientX;
    const startRatio = splitRatio;
    const bodyWidth = bodyRef.current?.offsetWidth ?? 1;
    const sign = chatLayoutReversed ? -1 : 1;
    document.body.style.userSelect = 'none';
    document.body.style.cursor = 'col-resize';

    const onMove = (ev: MouseEvent) => {
      if (!draggingRef.current) return;
      const dx = (ev.clientX - startX) * sign;
      const newRatio = Math.min(80, Math.max(20, startRatio + (dx / bodyWidth) * 100));
      setSplitRatio(newRatio);
    };
    const onUp = () => {
      draggingRef.current = false;
      document.body.style.userSelect = '';
      document.body.style.cursor = '';
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);
    };
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
  }, [splitRatio, chatLayoutReversed]);

  useEffect(() => {
    return () => {
      draggingRef.current = false;
      document.body.style.userSelect = '';
      document.body.style.cursor = '';
    };
  }, []);

  return (
    <div className="chat-layout">
      <div className="chat-body" ref={bodyRef} style={{ flexDirection: chatLayoutReversed ? 'row-reverse' : 'row' }}>
        {/* Sidebar */}
        <div className={'chat-session-sidebar' + (sidebarCollapsed ? ' collapsed' : '')}>
          <div className="chat-session-header">
            <span className="chat-session-title">{t('chat.sessions', 'Sessions')}</span>
            <button
              className="btn-icon"
              onClick={newSession}
              disabled={loadingSession || messages.length === 0}
              title={t('chat.newSession', 'New Session')}
              style={{
                width: 22, height: 22, border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)',
                background: 'transparent', color: 'var(--text-muted)', cursor: 'pointer', fontSize: 'var(--fs-base)',
                display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
                opacity: loadingSession || messages.length === 0 ? 0.35 : 1,
              }}
            >+</button>
          </div>
          <SessionTree />
        </div>

        {/* Main chat area */}
        <div className="chat-left" style={{ width: `${splitRatio}%`, flex: 'none' }}>
          <div className="chat-header">
            <div className="chat-header-left">
              <button className="btn-collapse" onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
                title={sidebarCollapsed ? t('chat.expandSidebar', 'Expand') : t('chat.collapseSidebar', 'Collapse')}>
                {sidebarCollapsed ? '▶' : '◀'}
              </button>
              {activePreset !== '__chat__' && (
                <span className="chat-title">
                  {pipelines.find(p => p.name === activePreset)?.title || t('chat.title')}
                </span>
              )}
            </div>
            <div className="chat-header-right">
              <button className="btn btn-small btn-secondary" onClick={resetChat} title={t('common.reset')}>
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
            {mergedMessages.map((msg, i) => (
              <div key={msg.id || i} className={`chat-message ${msg.role}`}>
                <MessageBubble msg={msg} toolCalls={msg.toolCalls} />
              </div>
            ))}
          </div>

          <div className="chat-input-area">
            <textarea
              ref={textareaRef}
              className="chat-input"
              value={input}
              onChange={e => { setInput(e.target.value); autoResize(); }}
              onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); } }}
              placeholder={t('chat.placeholder')}
              rows={1}
              disabled={sending}
            />
            <button
              className={`btn btn-sm ${sending ? 'btn-danger' : 'btn-primary'}`}
              onClick={sending ? handleCancel : handleSend}
              disabled={!input.trim() && !sending}
              style={{ flexShrink: 0 }}
            >
              {sending ? t('chat.stop') : t('chat.send')}
            </button>
          </div>
        </div>

        <div className="chat-divider" onMouseDown={handleDividerMouseDown} />

        <EditorPanel />
      </div>
    </div>
  );
}
