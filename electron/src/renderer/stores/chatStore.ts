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
}

const streamStates: Record<number, StreamState> = {};
const processedEditIds = new Set<string>();

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
  send: (text: string) => Promise<void>;
  cancelChat: () => Promise<void>;
  resetChat: () => Promise<void>;
  setMessages: (msgs: ChatMessage[]) => void;
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

export const useChatStore = _create<ChatState>((set, get) => ({
  chatMessages: [],
  pendingEdits: [],
  currentSessionId: '',
  chatSessions: [],
  pipelineSessions: {},
  expandedNodes: new Set(['__chat__']),
  loadingSession: false,
  activePendingEdit: null,
  selectTreeNodes: [],

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
        set((s) => {
          const last = s.chatMessages[s.chatMessages.length - 1];
          if (last && last.role === 'assistant' && !last.content) {
            const msgs = s.chatMessages.slice(0, -1);
            return { chatMessages: [...msgs, { id: nextMsgId(), role: 'assistant', content: `Error: ${result.error ?? 'Unknown'}` }] };
          }
          return { chatMessages: [...s.chatMessages, { id: nextMsgId(), role: 'assistant', content: `Error: ${result.error ?? 'Unknown'}` }] };
        });
      }
    } catch (e) {
      set((s) => {
        const last = s.chatMessages[s.chatMessages.length - 1];
        if (last && last.role === 'assistant' && !last.content) {
          const msgs = s.chatMessages.slice(0, -1);
          return { chatMessages: [...msgs, { id: nextMsgId(), role: 'assistant', content: `Error: ${String(e)}` }] };
        }
        return { chatMessages: [...s.chatMessages, { id: nextMsgId(), role: 'assistant', content: `Error: ${String(e)}` }] };
      });
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
      if (result.ok) set({ chatMessages: [] });
    } catch (e) { console.error('Chat reset failed:', e); }
  },

  setMessages: (msgs) => set({ chatMessages: msgs }),

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
        set({ currentSessionId: sessionId, chatMessages: r.session.messages || [] });
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
    // Load sessions on first expand
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
      if (ti != null && streamStates[ti]) {
        streamStates[ti].complete = true;
      }
      set((s) => ({
        chatMessages: [...s.chatMessages, { id: nextMsgId(), role: 'assistant', content: `[Error] ${(event.message as string) || ''}` }],
      }));
      return;
    }

    // ── chat.stream_start ──
    if (et === 'chat.stream_start') {
      const ti = event.turn_index as number;
      streamStates[ti] = { accumulating: '', reasoningParts: [], toolAnnotation: '', complete: false };
      // Prune stale states (>20 turns old)
      for (const k of Object.keys(streamStates)) {
        const n = Number(k);
        if (!isNaN(n) && n < ti - 20) delete streamStates[n];
      }
      set((s) => {
        const last = s.chatMessages[s.chatMessages.length - 1];
        if (last && last.role === 'assistant' && !last.content) {
          return { chatMessages: [...s.chatMessages.slice(0, -1), { id: nextMsgId(), role: 'assistant', content: '' }] };
        }
        return { chatMessages: [...s.chatMessages, { id: nextMsgId(), role: 'assistant', content: '' }] };
      });
      return;
    }

    // ── chat.text_chunk ──
    if (et === 'chat.text_chunk') {
      const ti = event.turn_index as number;
      const content = (event.content as string) || '';
      const st = streamStates[ti] || { accumulating: '', reasoningParts: [], toolAnnotation: '', complete: false };
      streamStates[ti] = st;
      st.accumulating += content;
      set((s) => {
        const next = [...s.chatMessages];
        for (let i = next.length - 1; i >= 0; i--) {
          if (next[i].role === 'assistant') {
            next[i] = { ...next[i], content: st.toolAnnotation + st.accumulating };
            break;
          }
        }
        return { chatMessages: next };
      });
      return;
    }

    // ── chat.think_chunk ──
    if (et === 'chat.think_chunk') {
      const ti = event.turn_index as number;
      const content = (event.content as string) || '';
      const st = streamStates[ti] || { accumulating: '', reasoningParts: [], toolAnnotation: '', complete: false };
      streamStates[ti] = st;
      st.reasoningParts.push(content);
      set((s) => {
        const next = [...s.chatMessages];
        for (let i = next.length - 1; i >= 0; i--) {
          if (next[i].role === 'assistant') {
            next[i] = { ...next[i], reasoning: st.reasoningParts.join('') };
            break;
          }
        }
        return { chatMessages: next };
      });
      return;
    }

    // ── chat.tool_generated ──
    if (et === 'chat.tool_generated') {
      const toolName = (event.tool_name as string) || '';
      const ti = event.turn_index as number;
      if (ti != null) {
        const st = streamStates[ti] || { accumulating: '', reasoningParts: [], toolAnnotation: '', complete: false };
        streamStates[ti] = st;
        st.toolAnnotation = '\n\n[Calling ' + toolName + '...]';
      }
      set((s) => {
        const next = [...s.chatMessages];
        for (let i = next.length - 1; i >= 0; i--) {
          if (next[i].role === 'assistant') {
            const existing = next[i].content;
            const label = '[Calling ' + toolName + '...]';
            next[i] = { ...next[i], content: existing ? existing + '\n\n' + label : label };
            break;
          }
        }
        return { chatMessages: next };
      });
      return;
    }

    // ── chat.stream_end ──
    if (et === 'chat.stream_end') {
      const ti = event.turn_index as number;
      const st = streamStates[ti];
      if (st) {
        st.complete = true;
        set((s) => {
          const next = [...s.chatMessages];
          for (let i = next.length - 1; i >= 0; i--) {
            if (next[i].role === 'assistant') {
              next[i] = { ...next[i], content: st.toolAnnotation + (st.accumulating || next[i].content) };
              break;
            }
          }
          return { chatMessages: next };
        });
      }
      return;
    }

    // ── pipeline.edit ──
    if (et === 'pipeline.edit') {
      const editId = event.edit_id as string;
      if (editId && !processedEditIds.has(editId)) {
        processedEditIds.add(editId);
        const edit: PendingEdit = {
          edit_id: editId,
          original: (event.original as string) || '',
          modified: (event.modified as string) || '',
          explanation: (event.explanation as string) || '',
        };
        set((s) => ({ pendingEdits: [...s.pendingEdits, edit] }));
      } else if (editId) {
        set((s) => ({
          pendingEdits: s.pendingEdits.map(e =>
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

// Subscribe to changes to recompute selectTreeNodes and activePendingEdit
useChatStore.subscribe((s) => {
  // activePendingEdit — compare by edit_id to avoid reference inequality loops
  const active = s.pendingEdits.length > 0 ? s.pendingEdits[0] : null;
  const prevId = s.activePendingEdit?.edit_id ?? null;
  const nextId = active?.edit_id ?? null;
  if (prevId !== nextId) {
    useChatStore.setState({ activePendingEdit: active });
  }

  // selectTreeNodes — only rebuild when session data actually changes
  const pipelines = usePipelineStore.getState().pipelines;
  const key = `${s.chatSessions.length}|${Object.keys(s.pipelineSessions).length}|${pipelines.length}`;
  if (key !== _lastTreeNodesKey) {
    _lastTreeNodesKey = key;
    const nodes = _buildTreeNodes(s.chatSessions, s.pipelineSessions, pipelines.map(p => ({ name: p.name, title: p.title })));
    useChatStore.setState({ selectTreeNodes: nodes });
  }
});
