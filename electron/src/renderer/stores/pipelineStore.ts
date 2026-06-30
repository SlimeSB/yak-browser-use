import { _create } from './_factory';
import * as api from '../apiClient';
import type { PipelineMeta, EventData } from '../types';
import { interpolateTemplate } from '../utils/interpolate';
import { showAlert } from '../utils/dialog';

// ── Helpers ──────────────────────────────────────────────────

function getStepStatus(events: EventData[], pendingReview: unknown, name: string): 'done' | 'current' | 'pending' | 'error' | 'review' {
  const hasStart = events.some(e => e.type === 'step_start' && e.node_name === name);
  const hasEnd = events.some(e => e.type === 'step_end' && e.node_name === name);
  const hasError = events.some(e => e.type === 'step_error' && e.node_name === name);
  const hasReview = events.some(e => e.type === 'step_review_required' && e.node_name === name);
  if (hasError) return 'error';
  if (pendingReview && hasStart && !hasEnd) return 'review';
  if (hasStart && hasEnd) return 'done';
  if (hasStart && !hasEnd) return 'current';
  return 'pending';
}

// ── Types ────────────────────────────────────────────────────

export interface PendingReviewData {
  extraOps: Array<{ type: string; value?: string; selector?: string }>;
  reason: string;
  guardLayer: string;
  threadId: string;
}

interface PipelineState {
  pipelines: PipelineMeta[];
  activePreset: string;
  pipelineCache: Record<string, string>;
  pipelineEditor: string;
  events: EventData[];
  result: Record<string, unknown> | null;
  resultErrors: string[] | null;
  loading: boolean;
  currentRunId: string;
  currentPipeline: string;
  cancelling: boolean;
  pendingReview: PendingReviewData | null;
  reviewMode: string;
  params: Record<string, string>;
  // actions
  run: () => Promise<void>;
  cancel: () => Promise<void>;
  reviewApprove: (reason: string) => void;
  reviewReject: (reason: string) => void;
  addEvent: (type: string, node_name: string, data?: Record<string, unknown>) => void;
  handleRunEnd: () => Promise<void>;
  refreshPipelines: () => Promise<void>;
  deletePipeline: (name: string) => Promise<void>;
  savePipeline: () => Promise<void>;
  setActivePreset: (name: string) => void;
  setReviewMode: (mode: string) => void;
  setPendingReview: (pr: PendingReviewData | null) => void;
  setLoading: (v: boolean) => void;
  setCancelling: (v: boolean) => void;
  setPipelineEditor: (text: string) => void;
  setCurrentPipeline: (name: string) => void;
  setCurrentRunId: (id: string) => void;
  setResult: (r: Record<string, unknown> | null) => void;
  setResultErrors: (e: string[] | null) => void;
  clearEvents: () => void;
  setParam: (key: string, value: string) => void;
  getStepStatus: (name: string) => 'done' | 'current' | 'pending' | 'error' | 'review';
}

// ── Store ────────────────────────────────────────────────────

export const usePipelineStore = _create<PipelineState>((set, get) => ({
  pipelines: [],
  activePreset: '',
  pipelineCache: {},
  pipelineEditor: '',
  events: [],
  result: null,
  resultErrors: null,
  loading: false,
  currentRunId: '',
  currentPipeline: '',
  cancelling: false,
  pendingReview: null,
  reviewMode: 'none',
  params: {},

  // ── Pipeline CRUD ─────────────────────────────────────────

  refreshPipelines: async () => {
    const r = await api.listPipelines();
    set({ pipelines: r.pipelines });
  },

  deletePipeline: async (name) => {
    const r = await api.deletePipeline(name);
    if (r.ok) {
      if (get().activePreset === name) {
        set({ activePreset: '__chat__', pipelineEditor: '' });
      }
      await get().refreshPipelines();
    } else {
      showAlert(r.error || 'Delete failed');
    }
  },

  savePipeline: async () => {
    const { activePreset, pipelineEditor } = get();
    if (!activePreset || activePreset === '__chat__' || !pipelineEditor.trim()) return;
    try {
      const r = await api.savePipeline(activePreset, pipelineEditor);
      if (r.ok) {
        set((st) => ({ pipelineCache: { ...st.pipelineCache, [activePreset]: pipelineEditor } }));
        await get().refreshPipelines();
      } else {
        showAlert(r.error || 'Save failed');
      }
    } catch (e) {
      showAlert(String(e));
    }
  },

  // ── Run engine ────────────────────────────────────────────

  run: async () => {
    const s = get();
    const p = s.pipelines.find(t => t.name === s.activePreset);
    if (!p) return;

    const missingKeys: string[] = [];
    for (const key of Object.keys(p.inputs)) {
      if (!s.params[key]?.trim()) missingKeys.push(p.inputs[key]);
    }
    if (missingKeys.length > 0) {
      showAlert('Please fill in: ' + missingKeys.join(', '));
      return;
    }

    let pipelineContent = s.pipelineCache[s.activePreset];
    if (!pipelineContent) {
      try {
        const resp = await api.getPipeline(s.activePreset);
        if (resp.content) {
          pipelineContent = resp.content;
          set((st) => ({
            pipelineCache: { ...st.pipelineCache, [st.activePreset]: pipelineContent! },
            pipelineEditor: pipelineContent,
          }));
        } else {
          showAlert('Failed to load pipeline definition');
          return;
        }
      } catch (e) {
        showAlert('Failed to load pipeline');
        return;
      }
    }

    const pipelineResolved = interpolateTemplate(pipelineContent, s.params);
    const { reviewMode } = s;
    const pipelineWithMode = pipelineResolved.startsWith('---')
      ? pipelineResolved.replace(/^---\r?\n/, `---\nreview_mode: "${reviewMode}"\n`)
      : `---\nreview_mode: "${reviewMode}"\n${pipelineResolved}`;

    set({ loading: true, result: null, resultErrors: null, events: [] });

    try {
      get().addEvent('engine_start', 'pipeline', {});
      const resp = await api.runPipeline(pipelineWithMode, s.params);
      if (resp.run_id) set({ currentRunId: resp.run_id });
      if (resp.pipeline) set({ currentPipeline: resp.pipeline });
      if (resp.error) {
        get().addEvent('step_error', 'runner', { error: resp.error });
        set({ resultErrors: [resp.error] });
      } else if (resp.status === 'interrupted' && resp.data?.pending_review) {
        const pr = resp.data.pending_review as { extra_ops: Array<{ type: string; value?: string; selector?: string }>; reason: string; guard_layer: string };
        set({
          pendingReview: {
            extraOps: pr.extra_ops || [],
            reason: pr.reason || '',
            guardLayer: pr.guard_layer || '',
            threadId: resp.run_id || '',
          },
        });
        get().addEvent('step_review_required', 'pipeline', { reason: pr.reason });
      } else {
        set({ result: resp.data || {} });
        if (resp.errors?.length) set({ resultErrors: resp.errors });
        get().addEvent('engine_end', 'pipeline', { status: resp.status });
      }
    } catch (e) {
      get().addEvent('step_error', 'runner', { error: String(e) });
      set({ resultErrors: [String(e)] });
    } finally {
      set({ loading: false });
    }
  },

  cancel: async () => {
    const { currentPipeline, currentRunId } = get();
    if (!currentPipeline || !currentRunId) return;
    set({ cancelling: true });
    try {
      await api.cancelPipeline(currentPipeline, currentRunId);
      set({ loading: false, currentRunId: '', currentPipeline: '' });
    } catch (e) {
      console.error('Cancel failed: %s', String(e));
    } finally {
      set({ cancelling: false });
    }
  },

  reviewApprove: (reason) => {
    const pr = get().pendingReview;
    set({ pendingReview: null });
    if (pr?.threadId) {
      api.reviewPipeline(pr.threadId, 'approve', reason).catch((e) => console.error('Review approve failed: %s', String(e)));
    }
    get().addEvent('resume', 'pipeline', { action: 'approve', reason });
  },

  reviewReject: (reason) => {
    const pr = get().pendingReview;
    set({ pendingReview: null });
    if (pr?.threadId) {
      api.reviewPipeline(pr.threadId, 'reject', reason).catch((e) => console.error('Review reject failed: %s', String(e)));
    }
    get().addEvent('resume', 'pipeline', { action: 'reject', reason });
  },

  // ── Events ────────────────────────────────────────────────

  addEvent: (type, node_name, data = {}) => {
    set((st) => ({ events: [...st.events, { type, timestamp: new Date().toISOString(), node_name, data }] }));
  },

  handleRunEnd: async () => {
    set({ loading: false, currentRunId: '', currentPipeline: '' });
  },

  getStepStatus: (name) => {
    const s = get();
    return getStepStatus(s.events, s.pendingReview, name);
  },

  // ── Simple setters ────────────────────────────────────────

  setActivePreset: (name) => set({ activePreset: name }),
  setReviewMode: (mode) => set({ reviewMode: mode }),
  setPendingReview: (pr) => set({ pendingReview: pr }),
  setLoading: (v) => set({ loading: v }),
  setCancelling: (v) => set({ cancelling: v }),
  setPipelineEditor: (text) => set({ pipelineEditor: text }),
  setCurrentPipeline: (name) => set({ currentPipeline: name }),
  setCurrentRunId: (id) => set({ currentRunId: id }),
  setResult: (r) => set({ result: r }),
  setResultErrors: (e) => set({ resultErrors: e }),
  clearEvents: () => set({ events: [] }),
  setParam: (key, value) => set((st) => ({ params: { ...st.params, [key]: value } })),
}));
