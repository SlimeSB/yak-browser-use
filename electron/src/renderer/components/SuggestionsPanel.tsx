import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';

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
  const { t } = useTranslation();
  const [rejectReason, setRejectReason] = useState('');
  const [showingReject, setShowingReject] = useState(false);

  return (
    <div className="card" style={{ borderColor: '#f59e0b', borderWidth: 2 }}>
      <div className="card-title" style={{ color: '#f59e0b' }}>
        {t('log.pendingReview')}
        {guardLayer && <span style={{ fontSize: 10, marginLeft: 8 }}>[{guardLayer}]</span>}
      </div>
      <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 8 }}>
        {reason}
      </div>
      <div style={{ maxHeight: 120, overflow: 'auto', marginBottom: 8 }}>
        <table className="result-table" style={{ fontSize: 10 }}>
          <thead>
            <tr>
              <th>{t('log.type')}</th>
              <th>{t('log.selectorValue')}</th>
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
          {t('log.approve')}
        </button>
        {!showingReject ? (
          <button className="btn btn-danger btn-sm" onClick={() => setShowingReject(true)}>
            {t('log.reject')}
          </button>
        ) : (
          <div style={{ display: 'flex', gap: 4, flex: 1 }}>
            <input
              className="param-input"
              style={{ flex: 1 }}
              placeholder={t('log.reason') + t('log.required')}
              value={rejectReason}
              onChange={e => setRejectReason(e.target.value)}
            />
            <button
              className="btn btn-danger btn-sm"
              onClick={() => {
                if (!rejectReason.trim()) {
                  window.alert(t('log.reason') + t('log.required'));
                  return;
                }
                onReject(rejectReason);
                setShowingReject(false);
                setRejectReason('');
              }}
            >
              {t('log.confirmReject')}
            </button>
            <button
              className="btn btn-secondary btn-sm"
              onClick={() => { setShowingReject(false); setRejectReason(''); }}
            >
              {t('connection.cancel')}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
