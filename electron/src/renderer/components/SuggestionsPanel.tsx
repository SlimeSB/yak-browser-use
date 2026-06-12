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
        Pending Review
        {guardLayer && <span style={{ fontSize: 10, marginLeft: 8 }}>[{guardLayer}]</span>}
      </div>
      <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 8 }}>
        {reason}
      </div>
      <div style={{ maxHeight: 120, overflow: 'auto', marginBottom: 8 }}>
        <table className="result-table" style={{ fontSize: 10 }}>
          <thead>
            <tr>
              <th>Type</th>
              <th>Selector/Value</th>
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
          Approve
        </button>
        {!showingReject ? (
          <button className="btn btn-danger btn-sm" onClick={() => setShowingReject(true)}>
            Reject
          </button>
        ) : (
          <div style={{ display: 'flex', gap: 4, flex: 1 }}>
            <input
              className="param-input"
              style={{ flex: 1 }}
              placeholder="Rejection reason (required)"
              value={rejectReason}
              onChange={e => setRejectReason(e.target.value)}
            />
            <button
              className="btn btn-danger btn-sm"
              onClick={() => {
                if (!rejectReason.trim()) {
                  window.electronAPI.showAlert('Please provide a rejection reason');
                  return;
                }
                onReject(rejectReason);
                setShowingReject(false);
                setRejectReason('');
              }}
            >
              Confirm Reject
            </button>
            <button
              className="btn btn-secondary btn-sm"
              onClick={() => { setShowingReject(false); setRejectReason(''); }}
            >
              Cancel
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
