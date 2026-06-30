import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { usePipelineStore } from '../../stores/pipelineStore';
import EventLog from '../EventLog';
import ResultTable from '../ResultTable';
import DiffView from '../DiffView';

export default function LogTab() {
  const { t } = useTranslation();
  const currentRunId = usePipelineStore(s => s.currentRunId);
  const events = usePipelineStore(s => s.events);
  const onClearEvents = usePipelineStore(s => s.clearEvents);
  const result = usePipelineStore(s => s.result);
  const resultErrors = usePipelineStore(s => s.resultErrors);
  const loading = usePipelineStore(s => s.loading);
  const pendingReview = usePipelineStore(s => s.pendingReview);
  const getStepStatus = usePipelineStore(s => s.getStepStatus);
  const activePreset = usePipelineStore(s => s.activePreset);
  const pipelines = usePipelineStore(s => s.pipelines);

  const preset = pipelines.find(p => p.name === activePreset);

  const stageNames = events.filter(e => e.type === 'step_start').map(e => e.node_name);
  // deduplicate while preserving order
  const stepNames = [...new Set(stageNames)];
  const stepStarts = events.filter(e => e.type === 'step_start');
  const stepEnds = events.filter(e => e.type === 'step_end');

  const reviewApprove = usePipelineStore(s => s.reviewApprove);
  const reviewReject = usePipelineStore(s => s.reviewReject);

  const handleApprove = () => reviewApprove('approved via log');
  const handleReject = () => {
    if (!logRejectReason.trim()) return;
    reviewReject(logRejectReason.trim());
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
        <div className="log-sidebar-header">
          <span className="log-sidebar-title">{t('log.steps')}</span>
          {currentRunId && <span className="log-sidebar-meta">{currentRunId.slice(0, 8)}</span>}
        </div>
        <div className="log-steps">
          {stepNames.length === 0 ? (
            <div className="log-steps-empty">
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
          <span style={{ fontSize: 'var(--fs-sm)', fontWeight: 'var(--fw-semibold)', color: 'var(--text-secondary)' }}>{t('exec.liveLog')}</span>
          <span style={{ flex: 1 }} />
          <span style={{ fontSize: 'var(--fs-xs)', color: 'var(--text-muted)' }}>{events.length} {t('log.events')}</span>
          <button className="btn btn-secondary btn-xs" onClick={onClearEvents}>{t('log.clear')}</button>
        </div>
        {pendingReview && (
          <div className="review-card">
            <div className="review-card-header">
              <div className="review-card-title">
                <span>!</span> {t('log.pendingReview')}
              </div>
              <span style={{ fontSize: 'var(--fs-xs)', color: 'var(--text-muted)' }}>{pendingReview.guardLayer || t('log.guardian')}</span>
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
                <button className="btn btn-success btn-sm" onClick={handleApprove}>{t('log.approve')}</button>
                {!showingLogReject ? (
                  <button className="btn btn-danger btn-sm" onClick={() => setShowingLogReject(true)}>{t('log.reject')}</button>
                ) : (
                  <div style={{ display: 'flex', gap: 6, flex: 1 }}>
                    <input
                      className="param-input" style={{ flex: 1, fontSize: 'var(--fs-sm)' }}
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
            <div className="artifact-title">{t('log.viewDiff')}</div>
            <DiffView lines={diffLines} maxHeight={200} />
          </div>
        )}
        <div className="artifact-section">
          <div className="artifact-title">{t('log.artifacts')}</div>
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
          <div className="artifact-title">{t('log.summary')}</div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6, fontSize: 'var(--fs-sm)' }}>
            <div><span style={{ color: 'var(--text-muted)' }}>{t('log.step')}s</span> {stepEnds.length}/{stepStarts.length}</div>
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
