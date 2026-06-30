import { _create } from './_factory';
import * as api from '../apiClient';
import type { ChatMessage, SessionMeta, PendingEdit, TreeNode } from '../types';
import { nextMsgId } from '../types';
import { usePipelineStore } from './pipelineStore';

interface StreamState {
  accumulating: string;
  reasoningParts: string[];
  toolAnnotation: string;
  complete: boolean;
  assistantMsgId: string;
}

interface ChatState {
  chatMessages: ChatMessage[];
  pendingEdits: PendingEdit[];
  currentSessionId: string;
  chatSessions: SessionMeta[];
  pipelineSessions: Record<string, SessionMeta[]>;
  expandedNodes: Set<string>;
  loadingSession: boolean;
  activePendingEdit: PendingEdit | null;
  selectTreeNodes: TreeNode[];
  _streamStates: Record<number, StreamState>;
  _processedEditIds: Set<string>;
  _lastAssistantId: string | null;
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

function _makeEventData(event: Record<string, unknown>) {
  return {
    type: event.type as string,
    timestamp: (event.timestamp as string) || (event._ts != null ? new Date((event._ts as number) * 1000).toISOString() : new Date().toISOString()),
    node_name: (event.step || event.pipeline || '') as string,
    data: event,
  };
}

function _buildTreeNodes(chatSessions: SessionMeta[], pipelineSessions: Record<string, SessionMeta[]>, pipelines: { name: string; title: string }[]): TreeNode[] {
  const nodes: TreeNode[] = [
    {
      name: '__chat__',
      label: 'No Workspace',
      isPipeline: false,
      sessions: chatSessions,
    },
  ];
  for (const p of pipelines) {
    nodes.push({
      name: p.name,
      label: p.title || p.name,
      isPipeline: true,
      sessions: pipelineSessions[p.name] || [],
    });
  }
  return nodes;
}

type _SetFn = (partial: Partial<ChatState> | ((s: ChatState) => Partial<ChatState>)) => void;

function _patchAssistantMsg(set: _SetFn, get: () => ChatState, updater: (msg: ChatMessage) => ChatMessage) {
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

function _appendError(set: _SetFn, get: () => ChatState, errMsg: string) {
  set((s) => {
    const last = s.chatMessages[s.chatMessages.length - 1];
    if (last && last.role === 'assistant' && !last.content) {
      const msgs = s.chatMessages.slice(0, -1);
      return { chatMessages: [...msgs, { id: nextMsgId(), role: 'assistant', content: errMsg }] };
    }
    return { chatMessages: [...s.chatMessages, { id: nextMsgId(), role: 'assistant', content: errMsg }] };
  });
}

export const useChatStore = _create<ChatState>((set, get) => ({
  chatMessages: [],
  pendingEdits: [],
  currentSessionId: '',
  chatSessions: [],
  pipelineSessions: {},
  expandedNodes: new Set(['__chat__']),
  loadingSession: false,
  activePendingEdit: null,
  selectTreeNodes: _buildTreeNodes([], {}, []),
  _streamStates: {},
  _processedEditIds: new Set(),
  _lastAssistantId: null,

  send: async (text) => {
    if (!text.trim()) return;
    const msgId = nextMsgId();
    set((s) => ({ chatMessages: [...s.chatMessages, { id: msgId, role: 'user', content: text }] }));

    const pipelineName = usePipelineStore.getState().activePreset || undefined;
    try {
      const result = await api.chat(text, pipelineName);
      if (result.ok) {
        usePipelineStore.getState().refreshPipelines();
      } else {
        _appendError(set, get, `Error: ${result.error ?? 'Unknown'}`);
      }
    } catch (e) {
      _appendError(set, get, `Error: ${String(e)}`);
    }
  },

  cancelChat: async () => {
    try { await api.chatCancel(); } catch (e) { console.error('Chat cancel failed:', e); }
    set((s) => ({
      chatMessages: [...s.chatMessages, { id: nextMsgId(), role: 'system', content: 'Session interrupted' }],
    }));
  },

  resetChat: async () => {
    try {
      const result = await api.chatReset();
      if (result.ok) {
        set({
          chatMessages: [],
          _streamStates: {},
          _lastAssistantId: null,
        });
      }
    } catch (e) { console.error('Chat reset failed:', e); }
  },

  setMessages: (msgs) => set({ chatMessages: msgs }),

  loadSessions: async (pipelineName) => {
    const name = pipelineName || '__chat__';
    try {
      const r = await api.listSessions(name);
      const sessionsList = r.sessions || [];
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
      console.log('[newSession] pipeline=%s newId=%s', activePreset, r.session_id);
      if (r.session_id) {
        set({ currentSessionId: r.session_id, chatMessages: [] });
        const list = await api.listSessions(activePreset);
        const sessionsList = list.sessions || [];
        if (activePreset === '__chat__' || !activePreset) {
          set({ chatSessions: sessionsList });
        } else {
          set((s) => ({ pipelineSessions: { ...s.pipelineSessions, [activePreset]: sessionsList } }));
        }
      }
    } catch (e) { console.error('newSession failed: %s', String(e)); }
    finally { set({ loadingSession: false }); }
  },

  archiveSession: async (sessionId) => {
    if (!confirm('Archive this session?')) return;
    const activePreset = usePipelineStore.getState().activePreset;
    try {
      await api.archiveSession(activePreset, sessionId);
      const list = await api.listSessions(activePreset);
      const sessionsList = list.sessions || [];
      if (activePreset === '__chat__' || !activePreset) {
        set({ chatSessions: sessionsList });
      } else {
        set((s) => ({ pipelineSessions: { ...s.pipelineSessions, [activePreset]: sessionsList } }));
      }
      const { currentSessionId } = get();
      if (currentSessionId === sessionId) {
        const found = sessionsList.find(s => s.session_id !== sessionId);
        set({ currentSessionId: found?.session_id || '' });
      }
    } catch (e) { console.error('archiveSession failed: %s', String(e)); }
  },

  selectSession: async (sessionId) => {
    const activePreset = usePipelineStore.getState().activePreset;
    set({ loadingSession: true });
    try {
      const r = await api.getSessionData(activePreset, sessionId);
      console.log('[selectSession] pipeline=%s session=%s msgs=%d', activePreset, sessionId, r.session?.messages?.length || 0);
      if (r.session) {
        const raw: Record<string, unknown>[] = (r.session.messages || []) as any;
        const normalized: ChatMessage[] = raw.map((m) => ({
          id: (m.id as string) || nextMsgId(),
          role: (m.role as ChatMessage['role']) || 'assistant',
          content: (m.content as string) || '',
          reasoning: m.reasoning as string | undefined,
          toolName: (m.toolName as string) || (m.name as string) || '',
          toolCallId: (m.toolCallId as string) || (m.tool_call_id as string) || '',
          toolOk: m.toolOk !== undefined ? (m.toolOk as boolean) : (m.ok !== undefined ? (m.ok as boolean) : (typeof m.content === 'string' && m.role === 'tool' ? !m.content.startsWith('Error executing ') : undefined)),
          toolDuration: m.toolDuration !== undefined ? (m.toolDuration as number) : (m.duration_ms !== undefined ? (m.duration_ms as number) : undefined),
        }));
        set({ currentSessionId: sessionId, chatMessages: normalized });
      }
    } catch (e) { console.error('getSessionData failed: %s', String(e)); }
    finally { set({ loadingSession: false }); }
  },

  switchPipeline: async (pipelineName) => {
    const currentPreset = usePipelineStore.getState().activePreset;
    if (pipelineName === currentPreset) return;
    const prevPreset = currentPreset;
    usePipelineStore.getState().setActivePreset(pipelineName);
    set({ chatMessages: [], currentSessionId: '' });
    try {
      const r = await api.switchSession(pipelineName);
      const list = r.sessions || [];
      if (pipelineName === '__chat__' || !pipelineName) {
        set({ chatSessions: list });
      } else {
        set((s) => ({ pipelineSessions: { ...s.pipelineSessions, [pipelineName]: list } }));
      }
      if (list.length > 0) {
        set({ currentSessionId: list[0].session_id });
      }
    } catch (e) {
      console.error('switchSession failed: %s', String(e));
      usePipelineStore.getState().setActivePreset(prevPreset);
      if (pipelineName === '__chat__' || !pipelineName) {
        set({ chatSessions: [] });
      } else {
        set((s) => ({ pipelineSessions: { ...s.pipelineSessions, [pipelineName]: [] } }));
      }
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
    if (name !== '__chat__') {
      const s = get();
      if (!s.pipelineSessions[name]) {
        try {
          const r = await api.listSessions(name);
          const list = r.sessions || [];
          set((st) => ({ pipelineSessions: { ...st.pipelineSessions, [name]: list } }));
        } catch (e) { console.error('listSessions failed in toggleExpand: %s', String(e)); }
      }
    }
  },

  confirmEdit: async (editId) => {
    try {
      const result = await api.chatConfirm(editId);
      if (result.status === 'confirmed' || result.status === 'already_confirmed') {
        usePipelineStore.getState().refreshPipelines();
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
        usePipelineStore.getState().refreshPipelines();
        set((s) => ({ pendingEdits: s.pendingEdits.filter(e => e.edit_id !== editId) }));
        return null;
      }
      return result.error || 'Revert failed';
    } catch (e) { return String(e); }
  },

  handleWsEvent: (event) => {
    const et = event.type as string;

    // ── chat.tool_start ──
    if (et === 'chat.tool_start') {
      set((s) => ({
        chatMessages: [...s.chatMessages, {
          id: nextMsgId(), role: 'tool', content: '',
          toolName: (event.tool_name as string) || '',
          toolCallId: (event.id as string) || '',
          toolOk: undefined,
        }],
      }));
      usePipelineStore.getState().addEvent('chat.tool_start', (event.step || event.pipeline || '') as string, event as Record<string, unknown>);
      return;
    }

    // ── chat.tool_end ──
    if (et === 'chat.tool_end') {
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
      usePipelineStore.getState().addEvent('chat.tool_end', (event.step || event.pipeline || '') as string, event as Record<string, unknown>);
      return;
    }

    // ── chat.error ──
    if (et === 'chat.error') {
      const ti = event.turn_index as number;
      if (ti != null) {
        set((s) => {
          const st = s._streamStates[ti];
          if (st) {
            return { _streamStates: { ...s._streamStates, [ti]: { ...st, complete: true } } };
          }
          return {};
        });
      }
      set((s) => ({
        chatMessages: [...s.chatMessages, { id: nextMsgId(), role: 'assistant', content: `[Error] ${(event.message as string) || ''}` }],
      }));
      return;
    }

    // ── chat.stream_start ──
    if (et === 'chat.stream_start') {
      const ti = event.turn_index as number;
      const newId = nextMsgId();
      set((s) => {
        const streamStates = { ...s._streamStates, [ti]: { accumulating: '', reasoningParts: [], toolAnnotation: '', complete: false, assistantMsgId: newId } };
        for (const k of Object.keys(streamStates)) {
          const n = Number(k);
          if (!isNaN(n) && n < ti - 20) delete streamStates[n];
        }
        const last = s.chatMessages[s.chatMessages.length - 1];
        let chatMessages: ChatMessage[];
        if (last && last.role === 'assistant' && !last.content) {
          chatMessages = [...s.chatMessages.slice(0, -1), { id: newId, role: 'assistant', content: '' }];
        } else {
          chatMessages = [...s.chatMessages, { id: newId, role: 'assistant', content: '' }];
        }
        return { _streamStates: streamStates, chatMessages, _lastAssistantId: newId };
      });
      return;
    }

    // ── chat.text_chunk ──
    if (et === 'chat.text_chunk') {
      const ti = event.turn_index as number;
      const content = (event.content as string) || '';
      const st = get()._streamStates[ti];
      if (st) {
        const newSt = { ...st, accumulating: st.accumulating + content };
        set((s) => ({ _streamStates: { ...s._streamStates, [ti]: newSt } }));
        _patchAssistantMsg(set, get, (msg) => ({ ...msg, content: newSt.toolAnnotation + newSt.accumulating }));
      }
      return;
    }

    // ── chat.think_chunk ──
    if (et === 'chat.think_chunk') {
      const ti = event.turn_index as number;
      const content = (event.content as string) || '';
      const st = get()._streamStates[ti];
      if (st) {
        const newSt = { ...st, reasoningParts: [...st.reasoningParts, content] };
        set((s) => ({ _streamStates: { ...s._streamStates, [ti]: newSt } }));
        _patchAssistantMsg(set, get, (msg) => ({ ...msg, reasoning: newSt.reasoningParts.join('') }));
      }
      return;
    }

    // ── chat.tool_generated ──
    if (et === 'chat.tool_generated') {
      const toolName = (event.tool_name as string) || '';
      const ti = event.turn_index as number;
      if (ti != null) {
        const st = get()._streamStates[ti];
        if (st) {
          const newSt = { ...st, toolAnnotation: '\n\n[Calling ' + toolName + '...]' };
          set((s) => ({ _streamStates: { ...s._streamStates, [ti]: newSt } }));
        }
      }
      _patchAssistantMsg(set, get, (msg) => {
        const label = '[Calling ' + toolName + '...]';
        return { ...msg, content: msg.content ? msg.content + '\n\n' + label : label };
      });
      return;
    }

    // ── chat.stream_end ──
    if (et === 'chat.stream_end') {
      const ti = event.turn_index as number;
      const st = get()._streamStates[ti];
      if (st) {
        set((s) => ({ _streamStates: { ...s._streamStates, [ti]: { ...st, complete: true } } }));
        _patchAssistantMsg(set, get, (msg) => ({
          ...msg,
          content: st.toolAnnotation + (st.accumulating || msg.content),
        }));
      }
      return;
    }

    // ── pipeline.edit ──
    if (et === 'pipeline.edit') {
      const editId = event.edit_id as string;
      const s = get();
      if (editId && !s._processedEditIds.has(editId)) {
        const newSet = new Set(s._processedEditIds);
        newSet.add(editId);
        const edit: PendingEdit = {
          edit_id: editId,
          original: (event.original as string) || '',
          modified: (event.modified as string) || '',
          explanation: (event.explanation as string) || '',
        };
        set((st) => ({ _processedEditIds: newSet, pendingEdits: [...st.pendingEdits, edit] }));
      } else if (editId) {
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
  },
}));

let _lastTreeNodesKey = '';

useChatStore.subscribe((s) => {
  const active = s.pendingEdits.length > 0 ? s.pendingEdits[0] : null;
  const prevId = s.activePendingEdit?.edit_id ?? null;
  const nextId = active?.edit_id ?? null;
  if (prevId !== nextId) {
    useChatStore.setState({ activePendingEdit: active });
  }

  const pipelines = usePipelineStore.getState().pipelines;
  const key = `${s.chatSessions.length}|${Object.keys(s.pipelineSessions).length}|${pipelines.length}`;
  if (key !== _lastTreeNodesKey) {
    _lastTreeNodesKey = key;
    const nodes = _buildTreeNodes(s.chatSessions, s.pipelineSessions, pipelines.map(p => ({ name: p.name, title: p.title })));
    useChatStore.setState({ selectTreeNodes: nodes });
  }
});
