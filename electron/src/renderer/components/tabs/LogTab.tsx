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
          <span style={{ fontSize: 10, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px', color: 'var(--text-muted)' }}>步骤</span>
          {currentRunId && <span style={{ fontSize: 9, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>{currentRunId.slice(0, 8)}</span>}
        </div>
        <div className="log-steps">
          {stepNames.length === 0 ? (
            <div style={{ fontSize: 10, color: 'var(--text-muted)', textAlign: 'center', padding: 12 }}>
              暂无步骤数据
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
                    {status === 'done' ? '完成' : status === 'review' ? '待审批' : status === 'current' ? '执行中' : status === 'error' ? '失败' : '—'}
                  </span>
                </div>
              );
            })
          )}
        </div>
      </div>
      <div className="log-main">
        <div className="log-toolbar">
          <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)' }}>📋 实时日志</span>
          <span style={{ flex: 1 }} />
          <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>{events.length} 条日志</span>
          <button className="btn btn-secondary btn-xs" onClick={onClearEvents}>清空</button>
        </div>
        {pendingReview && (
          <div className="review-card">
            <div className="review-card-header">
              <div className="review-card-title">
                <span>⚠</span> 待审批操作
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
                <button className="btn btn-success btn-sm" onClick={handleApprove}>✓ 批准</button>
                {!showingLogReject ? (
                  <button className="btn btn-danger btn-sm" onClick={() => setShowingLogReject(true)}>✗ 拒绝</button>
                ) : (
                  <div style={{ display: 'flex', gap: 6, flex: 1 }}>
                    <input
                      className="param-input" style={{ flex: 1, fontSize: 11 }}
                      placeholder="拒绝理由（必填）"
                      value={logRejectReason}
                      onChange={e => setLogRejectReason(e.target.value)}
                      onKeyDown={e => { if (e.key === 'Enter') handleReject(); }}
                    />
                    <button className="btn btn-danger btn-sm" onClick={handleReject}>确认拒绝</button>
                    <button className="btn btn-secondary btn-sm" onClick={() => { setShowingLogReject(false); setLogRejectReason(''); }}>取消</button>
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
            <div className="artifact-title">📄 变更 diff</div>
            <DiffView lines={diffLines} maxHeight={200} />
          </div>
        )}
        <div className="artifact-section">
          <div className="artifact-title">📦 产物</div>
          {result ? (
            <ResultTable data={result} errors={resultErrors} />
          ) : (
            <div className="artifact-card">
              <div className="artifact-name">暂无产物</div>
              <div className="artifact-meta">执行管线后将在此显示结果</div>
            </div>
          )}
        </div>
        <div className="artifact-section">
          <div className="artifact-title">📊 摘要</div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6, fontSize: 11 }}>
            <div><span style={{ color: 'var(--text-muted)' }}>步骤</span> {stepEnds.length}/{stepStarts.length}</div>
            <div><span style={{ color: 'var(--text-muted)' }}>管线</span> {preset?.title || '—'}</div>
            <div><span style={{ color: 'var(--text-muted)' }}>日志数</span> {events.length}</div>
            <div><span style={{ color: 'var(--text-muted)' }}>状态</span>{' '}
              {loading ? <span style={{ color: 'var(--primary)' }}>运行中</span>
                : stepStarts.length > 0 ? <span style={{ color: 'var(--success)' }}>已完成</span>
                : <span style={{ color: 'var(--text-muted)' }}>就绪</span>}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
