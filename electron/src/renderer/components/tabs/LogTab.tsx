import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
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
  const { t } = useTranslation();
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
          <span style={{ fontSize: 10, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px', color: 'var(--text-muted)' }}>{t('log.steps')}</span>
          {currentRunId && <span style={{ fontSize: 9, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>{currentRunId.slice(0, 8)}</span>}
        </div>
        <div className="log-steps">
          {stepNames.length === 0 ? (
            <div style={{ fontSize: 10, color: 'var(--text-muted)', textAlign: 'center', padding: 12 }}>
              {t('log.noStepData')}
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
                    {status === 'done' ? t('stages.done') : status === 'review' ? t('log.pendingReview') : status === 'current' ? t('log.running') : status === 'error' ? t('stages.failed') : '—'}
                  </span>
                </div>
              );
            })
          )}
        </div>
      </div>
      <div className="log-main">
        <div className="log-toolbar">
          <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)' }}>📋 {t('exec.liveLog')}</span>
          <span style={{ flex: 1 }} />
          <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>{events.length} {t('log.events')}</span>
          <button className="btn btn-secondary btn-xs" onClick={onClearEvents}>{t('log.clear')}</button>
        </div>
        {pendingReview && (
          <div className="review-card">
            <div className="review-card-header">
              <div className="review-card-title">
                <span>⚠</span> {t('log.pendingReview')}
              </div>
              <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>{pendingReview.guardLayer || t('log.guardian')}</span>
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
                <button className="btn btn-success btn-sm" onClick={handleApprove}>✓ {t('log.approve')}</button>
                {!showingLogReject ? (
                  <button className="btn btn-danger btn-sm" onClick={() => setShowingLogReject(true)}>✗ {t('log.reject')}</button>
                ) : (
                  <div style={{ display: 'flex', gap: 6, flex: 1 }}>
                    <input
                      className="param-input" style={{ flex: 1, fontSize: 11 }}
                      placeholder={t('log.reason') + t('log.required')}
                      value={logRejectReason}
                      onChange={e => setLogRejectReason(e.target.value)}
                      onKeyDown={e => { if (e.key === 'Enter') handleReject(); }}
                    />
                    <button className="btn btn-danger btn-sm" onClick={handleReject}>{t('log.confirmReject')}</button>
                    <button className="btn btn-secondary btn-sm" onClick={() => { setShowingLogReject(false); setLogRejectReason(''); }}>{t('connection.cancel')}</button>
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
            <div className="artifact-title">📄 {t('log.viewDiff')}</div>
            <DiffView lines={diffLines} maxHeight={200} />
          </div>
        )}
        <div className="artifact-section">
          <div className="artifact-title">📦 {t('log.artifacts')}</div>
          {result ? (
            <ResultTable data={result} errors={resultErrors} />
          ) : (
            <div className="artifact-card">
              <div className="artifact-name">{t('log.noArtifacts')}</div>
              <div className="artifact-meta">{t('log.artifactsHint')}</div>
            </div>
          )}
        </div>
        <div className="artifact-section">
          <div className="artifact-title">📊 {t('log.summary')}</div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6, fontSize: 11 }}>
            <div><span style={{ color: 'var(--text-muted)' }}>{t('log.step')}s</span> {stepEnds.length}/{stepStarts.length}</div>
            <div><span style={{ color: 'var(--text-muted)' }}>{t('preset.pipeline')}</span> {preset?.title || '—'}</div>
            <div><span style={{ color: 'var(--text-muted)' }}>{t('log.events')}</span> {events.length}</div>
            <div><span style={{ color: 'var(--text-muted)' }}>{t('log.status')}</span>{' '}
              {loading ? <span style={{ color: 'var(--primary)' }}>{t('log.running')}</span>
                : stepStarts.length > 0 ? <span style={{ color: 'var(--success)' }}>{t('log.completed')}</span>
                : <span style={{ color: 'var(--text-muted)' }}>{t('statusBar.ready')}</span>}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
