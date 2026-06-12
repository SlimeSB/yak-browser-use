import React from 'react';
import type { PipelineMeta, EventData } from '../types';
import PresetSelectRow from '../PresetSelectRow';
import ParamsPanel from '../ParamsPanel';
import StageList from '../StageList';
import ProgressBar from '../ProgressBar';
import EventLog from '../EventLog';
import ResultTable from '../ResultTable';
import SuggestionsPanel from '../SuggestionsPanel';

interface ExecTabProps {
  activePreset: string;
  setActivePreset: (v: string) => void;
  pipelines: PipelineMeta[];
  loading: boolean;
  connected: boolean;
  currentRunId: string;
  cancelling: boolean;
  preset: PipelineMeta | undefined;
  params: Record<string, string>;
  pendingReview: {
    extraOps: Array<{ type: string; value?: string; selector?: string }>;
    reason: string;
    guardLayer: string;
    threadId: string;
  } | null;
  stages: string[];
  events: EventData[];
  result: Record<string, unknown> | null;
  resultErrors: string[] | null;
  onRun: () => void;
  onParamChange: (key: string, value: string) => void;
  onCancel: () => void;
  onReviewApprove: (reason: string) => void;
  onReviewReject: (reason: string) => void;
  onTabChange: (tab: string) => void;
}

export default function ExecTab({
  activePreset, setActivePreset, pipelines, loading, connected,
  currentRunId, cancelling, preset, params, pendingReview,
  stages, events, result, resultErrors,
  onRun, onParamChange, onCancel, onReviewApprove, onReviewReject, onTabChange,
}: ExecTabProps) {
  return (
    <div className="main-content">
      <div className="left-panel">
        <PresetSelectRow
          activeId={activePreset}
          pipelines={pipelines}
          onSelect={setActivePreset}
          onRun={onRun}
          loading={loading}
          connected={connected}
        />
        {loading && currentRunId && (
          <div style={{ display: 'flex', gap: 6, justifyContent: 'center' }}>
            <button className="btn btn-danger btn-sm" onClick={onCancel} disabled={cancelling}>
              {cancelling ? 'Cancelling...' : '⏹ Cancel'}
            </button>
          </div>
        )}
        <div className="quick-actions">
          <button className="qa-btn" onClick={() => onTabChange('agentmd')}>📄 Generate agent.md</button>
          <button className="qa-btn" onClick={() => onTabChange('params')}>⚙ Manage Params</button>
          <button className="qa-btn" onClick={() => onTabChange('pipelines')}>📦 Manage Pipelines</button>
          <button className="qa-btn" onClick={() => onTabChange('settings')}>⚙ Settings</button>
        </div>
        {preset && (
          <ParamsPanel
            schema={preset.inputs}
            values={params}
            onChange={onParamChange}
          />
        )}
        {pendingReview && (
          <SuggestionsPanel
            extraOps={pendingReview.extraOps}
            reason={pendingReview.reason}
            guardLayer={pendingReview.guardLayer}
            onApprove={onReviewApprove}
            onReject={onReviewReject}
          />
        )}
      </div>
      <div className="right-panel">
        <StageList stages={stages} events={events} />
        <ProgressBar events={events} />
        <div className="card">
          <div className="card-title">Live Log</div>
          <EventLog events={events} maxHeight={140} />
        </div>
        <ResultTable data={result} errors={resultErrors} />
        {loading && (
          <div className="loading-overlay">
            <div className="spinner" /> Processing…
          </div>
        )}
      </div>
    </div>
  );
}
