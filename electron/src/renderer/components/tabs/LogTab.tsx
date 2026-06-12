import React, { useState } from 'react';
import type { PipelineMeta, EventData } from '../../types';
import EventLog from '../EventLog';
import ResultTable from '../ResultTable';
import DiffView from '../DiffView';

interface LogTabProps {
  currentRunId: string;
  stepNames: string[];
  getStepStatus: (name: string) => 'done' | 'current' | 'pending' | 'error' | 'review';
  events: EventData[];
  onClearEvents: () => void;
  result: Record<string, unknown> | null;
  resultErrors: string[] | null;
  loading: boolean;
  stepStarts: EventData[];
  stepEnds: EventData[];
  preset: PipelineMeta | undefined;
  pendingReview: {
    extraOps: Array<{ type: string; value?: string; selector?: string }>;
    reason: string;
    guardLayer: string;
    threadId: string;
  } | null;
  onReviewApprove: (reason: string) => void;
  onReviewReject: (reason: string) => void;
}

export default function LogTab({
  currentRunId, stepNames, getStepStatus,
  events, onClearEvents, result, resultErrors,
  loading, stepStarts, stepEnds, preset,
  pendingReview, onReviewApprove, onReviewReject,
}: LogTabProps) {
  const [logRejectReason, setLogRejectReason] = useState('');
  const [showingLogReject, setShowingLogReject] = useState(false);

  const handleApprove = () => onReviewApprove('approved via log');
  const handleReject = () => {
    if (!logRejectReason.trim()) return;
    onReviewReject(logRejectReason.trim());
    setShowingLogReject(false);
    setLogRejectReason('');
  };

  const diffLines = pendingReview ? [
    ...pendingReview.extraOps.map((op) => ({
      type: 'add' as const,
      line: `${op.type}${op.value ? ' → ' + op.value : ''}${op.selector ? ' #' + op.selector : ''}`,
    })),
  ] : [];

  return (
    <div className="log-layout">
      <div className="log-left">
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '8px 10px 4px', borderBottom: '1px solid var(--border)' }}>
          <span style={{ fontSize: 10, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px', color: 'var(--text-muted)' }}>Steps</span>
          {currentRunId && <span style={{ fontSize: 9, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>{currentRunId.slice(0, 8)}</span>}
        </div>
        <div className="log-steps">
          {stepNames.length === 0 ? (
            <div style={{ fontSize: 10, color: 'var(--text-muted)', textAlign: 'center', padding: 12 }}>
              No step data
            </div>
          ) : (
            stepNames.map((name, i) => {
              const status = getStepStatus(name);
              return (
                <div key={i} className={`log-step ${status}`}>
                  <span className={`log-step-icon ${status === 'review' ? 'current' : status}`}>
                    {status === 'done' ? '✓' : status === 'error' ? '✗' : status === 'review' ? '⚠' : status === 'current' ? '●' : `${i + 1}`}
                  </span>
                  <span className="log-step-name">{name}</span>
                  <span className="log-step-time">
                    {status === 'done' ? 'Done' : status === 'review' ? 'Pending Review' : status === 'current' ? 'Running' : status === 'error' ? 'Failed' : '—'}
                  </span>
                </div>
              );
            })
          )}
        </div>
      </div>
      <div className="log-main">
        <div className="log-toolbar">
          <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)' }}>📋 Live Log</span>
          <span style={{ flex: 1 }} />
          <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>{events.length} events</span>
          <button className="btn btn-secondary btn-xs" onClick={onClearEvents}>Clear</button>
        </div>
        {pendingReview && (
          <div className="review-card">
            <div className="review-card-header">
              <div className="review-card-title">
                <span>⚠</span> Pending Review
              </div>
              <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>{pendingReview.guardLayer || 'guardian'}</span>
            </div>
            <div className="review-card-body">
              <div className="review-card-reason">{pendingReview.reason}</div>
              {pendingReview.extraOps.length > 0 && (
                <div className="review-card-ops">
                  {pendingReview.extraOps.map((op, i) => (
                    <span key={i} className="review-card-op">
                      <span className="op-tag">{op.type}</span>
                      {op.value || op.selector || ''}
                    </span>
                  ))}
                </div>
              )}
              <div className="review-card-footer">
                <button className="btn btn-success btn-sm" onClick={handleApprove}>✓ Approve</button>
                {!showingLogReject ? (
                  <button className="btn btn-danger btn-sm" onClick={() => setShowingLogReject(true)}>✗ Reject</button>
                ) : (
                  <div style={{ display: 'flex', gap: 6, flex: 1 }}>
                    <input
                      className="param-input" style={{ flex: 1, fontSize: 11 }}
                      placeholder="Rejection reason (required)"
                      value={logRejectReason}
                      onChange={e => setLogRejectReason(e.target.value)}
                      onKeyDown={e => { if (e.key === 'Enter') handleReject(); }}
                    />
                    <button className="btn btn-danger btn-sm" onClick={handleReject}>Confirm Reject</button>
                    <button className="btn btn-secondary btn-sm" onClick={() => { setShowingLogReject(false); setLogRejectReason(''); }}>Cancel</button>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
        <EventLog events={events} />
      </div>
      <div className="log-right">
        {pendingReview && diffLines.length > 0 && (
          <div className="artifact-section">
            <div className="artifact-title">📄 Diff</div>
            <DiffView lines={diffLines} maxHeight={200} />
          </div>
        )}
        <div className="artifact-section">
          <div className="artifact-title">📦 Artifacts</div>
          {result ? (
            <ResultTable data={result} errors={resultErrors} />
          ) : (
            <div className="artifact-card">
              <div className="artifact-name">No artifacts</div>
              <div className="artifact-meta">Results will appear here after running a pipeline</div>
            </div>
          )}
        </div>
        <div className="artifact-section">
          <div className="artifact-title">📊 Summary</div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6, fontSize: 11 }}>
            <div><span style={{ color: 'var(--text-muted)' }}>Steps</span> {stepEnds.length}/{stepStarts.length}</div>
            <div><span style={{ color: 'var(--text-muted)' }}>Pipeline</span> {preset?.title || '—'}</div>
            <div><span style={{ color: 'var(--text-muted)' }}>Events</span> {events.length}</div>
            <div><span style={{ color: 'var(--text-muted)' }}>Status</span>{' '}
              {loading ? <span style={{ color: 'var(--primary)' }}>Running</span>
                : stepStarts.length > 0 ? <span style={{ color: 'var(--success)' }}>Completed</span>
                : <span style={{ color: 'var(--text-muted)' }}>Ready</span>}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
