import { _create } from './_factory';
import * as api from '../apiClient';
import type { ChatMessage, SessionMeta, PendingEdit } from '../types';
import { nextMsgId } from '../types';
import { useConnectionStore } from './connectionStore';
import { usePipelineStore } from './pipelineStore';

// ── Types ────────────────────────────────────────────────────

interface StreamState {
  accumulating: string;
  reasoningParts: string[];
  toolAnnotation: string;
  complete: boolean;
  assistantMsgId: string;
}

interface ChatState {
  // data
  chatMessages: ChatMessage[];
  pendingEdits: PendingEdit[];
  currentSessionId: string;
  chatSessions: SessionMeta[];
  pipelineSessions: Record<string, SessionMeta[]>;
  expandedNodes: Set<string>;
  loadingSession: boolean;
  activePendingEdit: PendingEdit | null;
  // internal
  _streamStates: Record<number, StreamState>;
  _processedEditIds: Set<string>;
  _lastAssistantId: string | null;
  _streamingMsgIds: Set<string>;
  // actions
  send: (text: string) => Promise<void>;
  cancelChat: () => Promise<void>;
  resetChat: () => Promise<void>;
  setMessages: (msgs: ChatMessage[]) => void;
  loadSessions: (pipelineName: string) => Promise<void>;
  newSession: () => Promise<void>;
  archiveSession: (sessionId: string) => Promise<void>;
  selectSession: (sessionId: string) => Promise<void>;
  switchPipeline: (pipelineName: string) => Promise<void>;
  toggleExpand: (name: string) => Promise<void>;
  confirmEdit: (editId: string) => Promise<string | null>;
  revertEdit: (editId: string) => Promise<string | null>;
  handleWsEvent: (event: Record<string, unknown>) => void;
}

// ── Store ────────────────────────────────────────────────────

export const useChatStore = _create<ChatState>((set, get) => ({
  chatMessages: [],
  pendingEdits: [],
  currentSessionId: '',
  chatSessions: [],
  pipelineSessions: {},
  expandedNodes: new Set(['__chat__']),
  loadingSession: false,
  activePendingEdit: null,
  _streamStates: {},
  _processedEditIds: new Set(),
  _lastAssistantId: null,
  _streamingMsgIds: new Set(),

  // ── Chat send / receive ───────────────────────────────────

  send: async (text) => {
    if (!text.trim()) return;
    if (!useConnectionStore.getState().connected) {
      _appendError(set, get, 'Please connect to a browser first.');
      return;
    }
    const msgId = nextMsgId();
    set((s) => ({ chatMessages: [...s.chatMessages, { id: msgId, role: 'user', content: text }] }));

    const pipelineName = usePipelineStore.getState().activePreset || undefined;
    try {
      const result = await api.chat(text, pipelineName);
      if (result.ok) {
        await usePipelineStore.getState().refreshPipelines();
      } else {
        _appendError(set, get, `Error: ${result.error ?? 'Unknown'}`);
      }
    } catch (e) {
      _appendError(set, get, `Error: ${String(e)}`);
    }
  },

  cancelChat: async () => {
    try { await api.chatCancel(); } catch { /* ok */ }
    set((s) => {
      const streamingMsgIds = new Set(s._streamingMsgIds);
      const streamStates = { ...s._streamStates };
      for (const k of Object.keys(streamStates)) {
        const n = Number(k);
        streamStates[n] = { ...streamStates[n], complete: true };
        streamingMsgIds.delete(streamStates[n].assistantMsgId);
      }
      return {
        _streamStates: streamStates,
        _streamingMsgIds: streamingMsgIds,
        _lastAssistantId: null,
        chatMessages: [...s.chatMessages, { id: nextMsgId(), role: 'system', content: 'Session interrupted' }],
      };
    });
  },

  resetChat: async () => {
    try {
      const result = await api.chatReset();
      if (result.ok) {
        set({ chatMessages: [], _streamStates: {}, _lastAssistantId: null, _streamingMsgIds: new Set(), _processedEditIds: new Set() });
      }
    } catch (e) {
      console.error('Chat reset failed: %s', String(e));
    }
  },

  setMessages: (msgs) => set({ chatMessages: msgs }),

  // ── Session management ────────────────────────────────────

  loadSessions: async (pipelineName) => {
    const name = pipelineName || '__chat__';
    try {
      const r = await api.listSessions(name);
      const sessionsList = r.sessions ?? [];
      if (name === '__chat__' || !name) {
        set({ chatSessions: sessionsList });
      } else {
        set((s) => ({ pipelineSessions: { ...s.pipelineSessions, [name]: sessionsList } }));
      }
    } catch (e) {
      console.error('loadSessions failed: %s', String(e));
    }
  },

  newSession: async () => {
    const activePreset = usePipelineStore.getState().activePreset;
    set({ loadingSession: true });
    try {
      const r = await api.newSession(activePreset);
      if (r.session_id) {
        set({ currentSessionId: r.session_id, chatMessages: [] });
        const list = await api.listSessions(activePreset);
        const sessionsList = list.sessions ?? [];
        if (activePreset === '__chat__' || !activePreset) {
          set({ chatSessions: sessionsList });
        } else {
          set((s) => ({ pipelineSessions: { ...s.pipelineSessions, [activePreset]: sessionsList } }));
        }
      }
    } catch (e) {
      console.error('newSession failed: %s', String(e));
    } finally {
      set({ loadingSession: false });
    }
  },

  archiveSession: async (sessionId) => {
    if (!confirm('Archive this session?')) return;
    const activePreset = usePipelineStore.getState().activePreset;
    try {
      await api.archiveSession(activePreset, sessionId);
      const list = await api.listSessions(activePreset);
      const sessionsList = list.sessions ?? [];
      if (activePreset === '__chat__' || !activePreset) {
        set({ chatSessions: sessionsList });
      } else {
        set((s) => ({ pipelineSessions: { ...s.pipelineSessions, [activePreset]: sessionsList } }));
      }
      if (get().currentSessionId === sessionId) {
        const found = sessionsList.find(s => s.session_id !== sessionId);
        set({ currentSessionId: found?.session_id || '' });
      }
    } catch (e) {
      console.error('archiveSession failed: %s', String(e));
    }
  },

  selectSession: async (sessionId) => {
    const activePreset = usePipelineStore.getState().activePreset;
    set({ loadingSession: true });
    try {
      const r = await api.getSessionData(activePreset, sessionId);
      if (r.session) {
        const raw = (r.session.messages ?? []) as unknown as Record<string, unknown>[];
        set({
          currentSessionId: sessionId,
          chatMessages: raw.map(_normalizeMessage),
          _streamStates: {},
          _lastAssistantId: null,
          _streamingMsgIds: new Set(),
        });
      }
    } catch (e) {
      console.error('getSessionData failed: %s', String(e));
    } finally {
      set({ loadingSession: false });
    }
  },

  switchPipeline: async (pipelineName) => {
    const currentPreset = usePipelineStore.getState().activePreset;
    if (pipelineName === currentPreset) return;
    const prevPreset = currentPreset;

    usePipelineStore.getState().setActivePreset(pipelineName);
    set({ chatMessages: [], currentSessionId: '', _streamStates: {}, _lastAssistantId: null, _streamingMsgIds: new Set() });

    try {
      const r = await api.switchSession(pipelineName);
      const list = r.sessions ?? [];
      _setSessions(set, pipelineName, list);
      if (list.length > 0) {
        set({ currentSessionId: list[0].session_id });
      }
      // Expand the target node so its sessions are visible
      set((s) => {
        const next = new Set(s.expandedNodes);
        next.add(pipelineName);
        return { expandedNodes: next };
      });
    } catch (e) {
      console.error('switchSession failed: %s', String(e));
      usePipelineStore.getState().setActivePreset(prevPreset);
      _setSessions(set, pipelineName, []);
    }
  },

  toggleExpand: async (name) => {
    const currentPreset = usePipelineStore.getState().activePreset;

    if (name !== currentPreset) {
      await get().switchPipeline(name);
      set((s) => {
        const next = new Set(s.expandedNodes);
        next.add(name);
        return { expandedNodes: next };
      });
    } else {
      set((s) => {
        const next = new Set(s.expandedNodes);
        if (next.has(name)) next.delete(name);
        else next.add(name);
        return { expandedNodes: next };
      });
    }

    if (name !== '__chat__' && !get().pipelineSessions[name]) {
      try {
        const r = await api.listSessions(name);
        set((st) => ({
          pipelineSessions: { ...st.pipelineSessions, [name]: r.sessions ?? [] },
        }));
      } catch (e) {
        console.error('listSessions failed in toggleExpand: %s', String(e));
      }
    }
  },

  // ── Edit confirmation ─────────────────────────────────────

  confirmEdit: async (editId) => {
    try {
      const result = await api.chatConfirm(editId);
      if (result.status === 'confirmed' || result.status === 'already_confirmed') {
        await usePipelineStore.getState().refreshPipelines();
        set((s) => ({ pendingEdits: s.pendingEdits.filter(e => e.edit_id !== editId) }));
        return null;
      }
      return result.error || 'Confirm failed';
    } catch (e) { return String(e); }
  },

  revertEdit: async (editId) => {
    try {
      const result = await api.chatRevert(editId);
      if (result.status === 'reverted' || result.status === 'already_reverted') {
        await usePipelineStore.getState().refreshPipelines();
        set((s) => ({ pendingEdits: s.pendingEdits.filter(e => e.edit_id !== editId) }));
        return null;
      }
      return result.error || 'Revert failed';
    } catch (e) { return String(e); }
  },

  // ── WebSocket events ──────────────────────────────────────

  handleWsEvent: (event) => {
    _handleChatEvent(set, get, event);
  },
}));

// ── Module-level init signal ─────────────────────────────────

let _initDone = false;
if (import.meta.hot) {
  import.meta.hot.dispose(() => { _initDone = false; });
}

// ── Subscribe: active pending edit tracking ──────────────────

useChatStore.subscribe((s) => {
  const active = s.pendingEdits.length > 0 ? s.pendingEdits[0] : null;
  const prevId = s.activePendingEdit?.edit_id ?? null;
  const nextId = active?.edit_id ?? null;
  if (prevId !== nextId) {
    useChatStore.setState({ activePendingEdit: active });
  }
});

// ── Helpers ──────────────────────────────────────────────────

type SetFn = (partial: Partial<ChatState> | ((s: ChatState) => Partial<ChatState>)) => void;
type GetFn = () => ChatState;

function _setSessions(set: SetFn, pipelineName: string, list: SessionMeta[]) {
  if (pipelineName === '__chat__' || !pipelineName) {
    set({ chatSessions: list });
  } else {
    set((s) => ({ pipelineSessions: { ...s.pipelineSessions, [pipelineName]: list } }));
  }
}

function _normalizeMessage(m: Record<string, unknown>): ChatMessage {
  return {
    id: (m.id as string) || nextMsgId(),
    role: (m.role as ChatMessage['role']) || 'assistant',
    content: (m.content as string) || '',
    reasoning: m.reasoning as string | undefined,
    toolName: (m.toolName as string) || (m.name as string) || '',
    toolCallId: (m.toolCallId as string) || (m.tool_call_id as string) || '',
    toolOk: m.toolOk !== undefined
      ? (m.toolOk as boolean)
      : (m.ok !== undefined ? (m.ok as boolean) : undefined),
    toolDuration: m.toolDuration !== undefined
      ? (m.toolDuration as number)
      : (m.duration_ms !== undefined ? (m.duration_ms as number) : undefined),
  };
}

function _patchAssistantMsg(set: SetFn, get: GetFn, updater: (msg: ChatMessage) => ChatMessage) {
  const lastId = get()._lastAssistantId;
  set((s) => {
    const next = [...s.chatMessages];
    if (lastId) {
      const idx = next.findIndex(m => m.id === lastId);
      if (idx >= 0 && next[idx].role === 'assistant') {
        next[idx] = updater(next[idx]);
        return { chatMessages: next };
      }
    }
    for (let i = next.length - 1; i >= 0; i--) {
      if (next[i].role === 'assistant') {
        next[i] = updater(next[i]);
        break;
      }
    }
    return { chatMessages: next };
  });
}

function _appendError(set: SetFn, get: GetFn, errMsg: string) {
  set((s) => {
    const last = s.chatMessages[s.chatMessages.length - 1];
    if (last && last.role === 'assistant' && !last.content) {
      const msgs = s.chatMessages.slice(0, -1);
      return { chatMessages: [...msgs, { id: nextMsgId(), role: 'assistant', content: errMsg }] };
    }
    return { chatMessages: [...s.chatMessages, { id: nextMsgId(), role: 'assistant', content: errMsg }] };
  });
}

function _makeEventData(event: Record<string, unknown>) {
  return {
    type: event.type as string,
    timestamp: (event.timestamp as string) || (event._ts != null ? new Date((event._ts as number) * 1000).toISOString() : new Date().toISOString()),
    node_name: (event.step || event.pipeline || '') as string,
    data: event,
  };
}

// ── WebSocket event handler ──────────────────────────────────

function _handleChatEvent(set: SetFn, get: GetFn, event: Record<string, unknown>) {
  const et = event.type as string;
  const usePipeline = usePipelineStore.getState();

  switch (et) {
    case 'chat.tool_start':
      set((s) => ({
        chatMessages: [...s.chatMessages, {
          id: nextMsgId(), role: 'tool', content: '',
          toolName: (event.tool_name as string) || '',
          toolCallId: (event.id as string) || '',
          toolOk: undefined,
        }],
      }));
      usePipeline.addEvent('chat.tool_start', (event.step || event.pipeline || '') as string, event);
      return;

    case 'chat.tool_end': {
      const toolCallId = (event.id as string) || '';
      set((s) => {
        const next = [...s.chatMessages];
        for (let i = next.length - 1; i >= 0; i--) {
          if (next[i].role === 'tool' && next[i].toolCallId === toolCallId) {
            next[i] = {
              ...next[i],
              toolOk: event.ok as boolean,
              toolDuration: event.duration_ms as number,
              content: (event.result as string) || (event.error as string) || (event.ok ? 'Done' : 'Failed'),
            };
            break;
          }
        }
        return { chatMessages: next };
      });
      usePipeline.addEvent('chat.tool_end', (event.step || event.pipeline || '') as string, event);
      return;
    }

    case 'chat.error': {
      const ti = event.turn_index as number;
      if (ti != null) {
        const st = get()._streamStates[ti];
        if (st) {
          set((s) => {
            const streamingMsgIds = new Set(s._streamingMsgIds);
            if (st.assistantMsgId) streamingMsgIds.delete(st.assistantMsgId);
            return {
              _streamStates: _pruneStreamStates({ ...s._streamStates, [ti]: { ...st, complete: true } }, ti),
              _streamingMsgIds: streamingMsgIds,
            };
          });
        }
      } else {
        // No turn_index: clean up ALL active streams to be safe
        set((s) => {
          const streamingMsgIds = new Set(s._streamingMsgIds);
          const streamStates = { ...s._streamStates };
          for (const k of Object.keys(streamStates)) {
            const n = Number(k);
            streamStates[n] = { ...streamStates[n], complete: true };
            streamingMsgIds.delete(streamStates[n].assistantMsgId);
          }
          return { _streamStates: streamStates, _streamingMsgIds: streamingMsgIds };
        });
      }
      set((s) => ({
        chatMessages: [...s.chatMessages, { id: nextMsgId(), role: 'assistant', content: `❌ ${(event.message as string) || '未知错误'}` }],
      }));
      return;
    }

    case 'session.state': {
      const status = event.status as string;
      if (status === 'cancelled') {
        set((s) => {
          const streamStates = { ...s._streamStates };
          const streamingMsgIds = new Set(s._streamingMsgIds);
          const hadActiveStreams = Object.keys(streamStates).length > 0;
          for (const k of Object.keys(streamStates)) {
            const n = Number(k);
            const st = streamStates[n];
            streamStates[n] = { ...st, complete: true };
            streamingMsgIds.delete(st.assistantMsgId);
          }
          const partial: Partial<ChatState> = {
            _streamStates: streamStates,
            _streamingMsgIds: streamingMsgIds,
          };
          // Only add a cancellation bubble when the server-side cancel
          // reached us before cancelChat() had a chance to clean up
          // locally.  If streams were already cleared, cancelChat()
          // already appended its own "Session interrupted" message.
          if (hadActiveStreams) {
            partial.chatMessages = [...s.chatMessages, {
              id: nextMsgId(), role: 'assistant',
              content: '❌ 对话被中断（可能达到迭代上限或用户取消）',
            }];
          }
          return partial;
        });
      }
      return;
    }

    case 'chat.stream_start': {
      const ti = event.turn_index as number;
      const newId = nextMsgId();
      set((s) => {
        const streamStates = _pruneStreamStates({ ...s._streamStates, [ti]: { accumulating: '', reasoningParts: [], toolAnnotation: '', complete: false, assistantMsgId: newId } }, ti);
        const last = s.chatMessages[s.chatMessages.length - 1];
        let chatMessages: ChatMessage[];
        if (last && last.role === 'assistant' && !last.content) {
          chatMessages = [...s.chatMessages.slice(0, -1), { id: newId, role: 'assistant', content: '' }];
        } else {
          chatMessages = [...s.chatMessages, { id: newId, role: 'assistant', content: '' }];
        }
        const streamingMsgIds = new Set(s._streamingMsgIds);
        streamingMsgIds.add(newId);
        return { _streamStates: streamStates, chatMessages, _lastAssistantId: newId, _streamingMsgIds: streamingMsgIds };
      });
      return;
    }

    case 'chat.text_chunk': {
      const ti = event.turn_index as number;
      const content = (event.content as string) || '';
      const st = get()._streamStates[ti];
      if (st) {
        const newSt = { ...st, accumulating: st.accumulating + content };
        const newContent = newSt.toolAnnotation + newSt.accumulating;
        const lastId = st.assistantMsgId;
        set((s) => {
          const streamStates = _pruneStreamStates({ ...s._streamStates, [ti]: newSt }, ti);
          const next = [...s.chatMessages];
          let patched = false;
          if (lastId) {
            const idx = next.findIndex(m => m.id === lastId);
            if (idx >= 0 && next[idx].role === 'assistant') {
              next[idx] = { ...next[idx], content: newContent };
              patched = true;
            }
          }
          if (!patched) {
            for (let i = next.length - 1; i >= 0; i--) {
              if (next[i].role === 'assistant') {
                next[i] = { ...next[i], content: newContent };
                break;
              }
            }
          }
          return { _streamStates: streamStates, chatMessages: next };
        });
      }
      return;
    }

    case 'chat.think_chunk': {
      const ti = event.turn_index as number;
      const content = (event.content as string) || '';
      const st = get()._streamStates[ti];
      if (st) {
        const newSt = { ...st, reasoningParts: [...st.reasoningParts, content] };
        const newReasoning = newSt.reasoningParts.join('');
        const lastId = st.assistantMsgId;
        set((s) => {
          const streamStates = { ...s._streamStates, [ti]: newSt };
          const next = [...s.chatMessages];
          let patched = false;
          if (lastId) {
            const idx = next.findIndex(m => m.id === lastId);
            if (idx >= 0 && next[idx].role === 'assistant') {
              next[idx] = { ...next[idx], reasoning: newReasoning };
              patched = true;
            }
          }
          if (!patched) {
            for (let i = next.length - 1; i >= 0; i--) {
              if (next[i].role === 'assistant') {
                next[i] = { ...next[i], reasoning: newReasoning };
                break;
              }
            }
          }
          return { _streamStates: streamStates, chatMessages: next };
        });
      }
      return;
    }

    case 'chat.tool_generated': {
      const toolName = (event.tool_name as string) || '';
      const ti = event.turn_index as number;
      if (ti != null) {
        const st = get()._streamStates[ti];
        if (st) {
          const newSt = { ...st, toolAnnotation: `\n\n[Calling ${toolName}...]` };
          const lastId = st.assistantMsgId;
          set((s) => {
            const streamStates = { ...s._streamStates, [ti]: newSt };
            const next = [...s.chatMessages];
            const append = `\n\n[Calling ${toolName}...]`;
            let patched = false;
            if (lastId) {
              const idx = next.findIndex(m => m.id === lastId);
              if (idx >= 0 && next[idx].role === 'assistant') {
                next[idx] = { ...next[idx], content: next[idx].content ? next[idx].content + append : append };
                patched = true;
              }
            }
            if (!patched) {
              for (let i = next.length - 1; i >= 0; i--) {
                if (next[i].role === 'assistant') {
                  next[i] = { ...next[i], content: next[i].content ? next[i].content + append : append };
                  break;
                }
              }
            }
            return { _streamStates: streamStates, chatMessages: next };
          });
        }
      }
      return;
    }

    case 'chat.stream_end': {
      const ti = event.turn_index as number;
      const st = get()._streamStates[ti];
      if (st) {
        set((s) => {
          const streamingMsgIds = new Set(s._streamingMsgIds);
          if (st.assistantMsgId) streamingMsgIds.delete(st.assistantMsgId);
          return {
            _streamStates: { ...s._streamStates, [ti]: { ...st, complete: true } },
            _streamingMsgIds: streamingMsgIds,
          };
        });
        _patchAssistantMsg(set, get, (msg) => ({
          ...msg,
          content: st.toolAnnotation + (st.accumulating || msg.content),
        }));
      }
      return;
    }

    case 'pipeline.edit': {
      const editId = event.edit_id as string;
      if (!editId) return;
      const s = get();
      if (!s._processedEditIds.has(editId)) {
        const newSet = new Set(s._processedEditIds);
        newSet.add(editId);
        set((st) => ({
          _processedEditIds: newSet,
          pendingEdits: [...st.pendingEdits, {
            edit_id: editId,
            original: (event.original as string) || '',
            modified: (event.modified as string) || '',
            explanation: (event.explanation as string) || '',
          }],
        }));
      } else {
        set((st) => ({
          pendingEdits: st.pendingEdits.map(e =>
            e.edit_id === editId
              ? { ...e, modified: (event.modified as string) || e.modified, explanation: (event.explanation as string) || e.explanation }
              : e
          ),
        }));
      }
      return;
    }
  }
}

// ── Helpers ──────────────────────────────────────────────────

function _pruneStreamStates(states: Record<number, StreamState>, currentTurn: number): Record<number, StreamState> {
  // NOTE: mutates the input object in-place.  All callers pass a fresh
  // spread copy ({ ...s._streamStates, ... }) so no external state is
  // affected, but this function does NOT produce a new object.
  for (const k of Object.keys(states)) {
    const n = Number(k);
    if (!isNaN(n) && n < currentTurn - 20) delete states[n];
  }
  return states;
}
