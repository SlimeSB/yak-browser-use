import React, { useState, useRef, useEffect, useMemo, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { useChatStore } from '../../stores/chatStore';
import type { ChatMessage, TreeNode } from '../../types';
import { useConnectionStore } from '../../stores/connectionStore';
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
  const selectSession = useChatStore(s => s.selectSession);
  const switchPipeline = useChatStore(s => s.switchPipeline);
  const newSession = useChatStore(s => s.newSession);
  const archiveSession = useChatStore(s => s.archiveSession);

  const treeNodes = useMemo((): TreeNode[] => {
    const nodes: TreeNode[] = [
      { name: '__chat__', label: t('chat.noWorkspace'), sessions: chatSessions },
    ];
    for (const p of pipelines) {
      nodes.push({
        name: p.name,
        label: p.title || p.name,
        sessions: pipelineSessions[p.name] ?? [],
      });
    }
    return nodes;
  }, [pipelines, chatSessions, pipelineSessions, t]);

  const formatLabel = (s: { session_id: string; created_at: string; message_count: number }) => {
    try {
      return `${s.created_at.slice(0, 16).replace('T', ' ')} (${s.message_count})`;
    } catch {
      return s.session_id.slice(-8);
    }
  };

  return (
    <div className="chat-session-list">
      {treeNodes.map((node) => (
        <div key={node.name} className="tree-node">
          <div
            className={'tree-node-header' + (activePreset === node.name ? ' active' : '')}
            onClick={async () => {
              if (node.name !== activePreset) {
                await switchPipeline(node.name);
                await newSession();
              } else {
                await newSession();
              }
            }}
          >
            <span className="tree-node-label">{node.label}</span>
            <span className="tree-node-badge">({node.sessions.length})</span>
          </div>
          <div className="tree-children">
            {node.sessions.map(s => (
              <div
                key={s.session_id}
                className={'tree-session' + (currentSessionId === s.session_id ? ' active' : '')}
                onClick={() => selectSession(s.session_id, node.name)}
              >
                <span className={'tree-session-dot' + (currentSessionId === s.session_id ? ' active-dot' : '')}>
                  {currentSessionId === s.session_id ? '●' : '○'}
                </span>
                <span className="tree-session-label">{formatLabel(s)}</span>
                <span className="tree-session-count">{t('chat.sessionCount', { count: s.message_count })}</span>
                <button
                  className="tree-session-archive"
                  title={t('chat.archiveSession', 'Archive')}
                  onClick={(e) => { e.stopPropagation(); archiveSession(s.session_id, node.name); }}
                >✕</button>
              </div>
            ))}
          </div>
        </div>
      ))}
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
  isStreaming?: boolean;
}

const MessageBubble = React.memo(function MessageBubble({ msg, toolCalls, isStreaming }: MessageBubbleProps) {
  const { t } = useTranslation();
  const [thinkExpanded, setThinkExpanded] = useState(false);

  if (msg.role === 'user') {
    return <div className="chat-user-bubble"><pre>{msg.content}</pre></div>;
  }

  if (msg.role === 'system') {
    return <div className="chat-system-msg"><pre>{msg.content}</pre></div>;
  }

  // assistant — during streaming show plain text (fast), after stream_end render Markdown
  const contentNode = (() => {
    if (!msg.content) return null;
    if (isStreaming) {
      return <pre className="chat-agent-content-streaming">{msg.content}</pre>;
    }
    return <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>;
  })();

  return (
    <>
      {msg.reasoning && msg.content && !toolCalls && (
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
      {contentNode && (
        <div className="chat-agent-content">{contentNode}</div>
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
});

// ── Main component ───────────────────────────────────────────

export default function ChatTab() {
  const { t } = useTranslation();
  const messages = useChatStore(s => s.chatMessages);
  const streamingMsgIds = useChatStore(s => s._streamingMsgIds);
  const currentSessionId = useChatStore(s => s.currentSessionId);
  const pendingEdit = useChatStore(s => s.activePendingEdit);
  const pipelines = usePipelineStore(s => s.pipelines);
  const activePreset = usePipelineStore(s => s.activePreset);
  const loadingSession = useChatStore(s => s.loadingSession);

  const browserConnected = useConnectionStore(s => s.connected);
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

  // Auto-load sessions on mount
  useEffect(() => { loadSessions(activePreset); }, []);

  // Expand all pipeline nodes by default
  useEffect(() => {
    const pipelineNames = pipelines.map(p => p.name);
    const current = useChatStore.getState().expandedNodes;
    const needsUpdate = pipelineNames.some(n => !current.has(n));
    if (needsUpdate) {
      const next = new Set(current);
      for (const n of pipelineNames) next.add(n);
      useChatStore.setState({ expandedNodes: next });
    }
  }, [pipelines]);

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
        if (!msg.content && tools.length > 0 && result.length > 0) {
          const prev = result[result.length - 1];
          if (prev.role === 'assistant' && prev.toolCalls) {
            prev.reasoning = undefined;
            prev.toolCalls = [...prev.toolCalls, ...tools];
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

  // Auto-scroll — deferred to rAF to avoid layout thrashing during streaming
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    let rafId: number;
    const check = () => {
      rafId = 0;
      if (el.scrollHeight - el.scrollTop - el.clientHeight < 100) {
        el.scrollTop = el.scrollHeight;
      }
    };
    rafId = requestAnimationFrame(check);
    return () => { if (rafId) cancelAnimationFrame(rafId); };
  }, [messages]);

  // Force scroll to bottom when switching sessions
  useEffect(() => {
    if (!currentSessionId) return;
    const el = scrollRef.current;
    if (!el) return;
    const timer = setTimeout(() => {
      el.scrollTop = el.scrollHeight;
    }, 50);
    return () => clearTimeout(timer);
  }, [currentSessionId]);

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
    if (textareaRef.current) textareaRef.current.style.height = '';
    sendingRef.current = true;
    setSending(true);
    await send(text);
    sendingRef.current = false;
    setSending(false);
  };

  const handleCancel = async () => {
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
                background: 'transparent', color: 'var(--text)', cursor: 'pointer', fontSize: 'var(--fs-base)',
                display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
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
              <span className="chat-title">
                {activePreset === '__chat__'
                  ? t('chat.noWorkspace')
                  : pipelines.find(p => p.name === activePreset)?.title || t('chat.title')}
              </span>
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
                <MessageBubble msg={msg} toolCalls={msg.toolCalls} isStreaming={streamingMsgIds.has(msg.id)} />
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
              placeholder={browserConnected ? t('chat.placeholder') : t('chat.placeholderDisconnected')}
              rows={1}
              disabled={!browserConnected || sending}
            />
            <button
              className={`btn btn-sm ${sending ? 'btn-danger' : 'btn-primary'}`}
              onClick={sending ? handleCancel : handleSend}
              disabled={!browserConnected || (!input.trim() && !sending)}
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
