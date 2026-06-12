import React, { useState } from 'react';

interface SuggestionsPanelProps {
  extraOps: Array<{ type: string; value?: string; selector?: string }>;
  reason: string;
  guardLayer: string;
  onApprove: (reason: string) => void;
  onReject: (reason: string) => void;
}

export default function SuggestionsPanel({
  extraOps, reason, guardLayer, onApprove, onReject,
}: SuggestionsPanelProps) {
  const [rejectReason, setRejectReason] = useState('');
  const [showingReject, setShowingReject] = useState(false);

  return (
    <div className="card" style={{ borderColor: '#f59e0b', borderWidth: 2 }}>
      <div className="card-title" style={{ color: '#f59e0b' }}>
        待审批操作
        {guardLayer && <span style={{ fontSize: 10, marginLeft: 8 }}>[{guardLayer}]</span>}
      </div>
      <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 8 }}>
        {reason}
      </div>
      <div style={{ maxHeight: 120, overflow: 'auto', marginBottom: 8 }}>
        <table className="result-table" style={{ fontSize: 10 }}>
          <thead>
            <tr>
              <th>类型</th>
              <th>选择器/值</th>
            </tr>
          </thead>
          <tbody>
            {extraOps.map((op, i) => (
              <tr key={i}>
                <td>{op.type}</td>
                <td>{op.value || op.selector || ''}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
        <button
          className="btn btn-primary btn-sm"
          onClick={() => onApprove('approved via UI')}
        >
          批准
        </button>
        {!showingReject ? (
          <button className="btn btn-danger btn-sm" onClick={() => setShowingReject(true)}>
            拒绝
          </button>
        ) : (
          <div style={{ display: 'flex', gap: 4, flex: 1 }}>
            <input
              className="param-input"
              style={{ flex: 1 }}
              placeholder="拒绝理由（必填）"
              value={rejectReason}
              onChange={e => setRejectReason(e.target.value)}
            />
            <button
              className="btn btn-danger btn-sm"
              onClick={() => {
                if (!rejectReason.trim()) {
                  window.electronAPI.showAlert('请填写拒绝理由');
                  return;
                }
                onReject(rejectReason);
                setShowingReject(false);
                setRejectReason('');
              }}
            >
              确认拒绝
            </button>
            <button
              className="btn btn-secondary btn-sm"
              onClick={() => { setShowingReject(false); setRejectReason(''); }}
            >
              取消
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
