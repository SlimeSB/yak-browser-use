import React from 'react';

interface SettingsTabProps {
  reviewMode: string;
  onReviewModeChange: (mode: string) => void;
}

export default function SettingsTab({
  reviewMode, onReviewModeChange,
}: SettingsTabProps) {
  return (
    <div className="set-layout">
      <div className="set-content">
        <div className="set-group">
          <div className="set-group-title">Review</div>
          <div className="set-row">
            <div>
              <div className="set-label">Review Mode</div>
              <div className="set-desc">
                {reviewMode === 'human' ? 'Manual approval for all operations' : reviewMode === 'llm' ? 'LLM auto-review' : 'Hybrid mode'}
              </div>
            </div>
            <div style={{ display: 'flex', gap: 4 }}>
              <button
                className={`btn btn-xs ${reviewMode === 'human' ? 'btn-primary' : 'btn-secondary'}`}
                onClick={() => onReviewModeChange('human')}
              >Manual</button>
              <button
                className={`btn btn-xs ${reviewMode === 'llm' ? 'btn-primary' : 'btn-secondary'}`}
                onClick={() => onReviewModeChange('llm')}
              >LLM</button>
              <button
                className={`btn btn-xs ${reviewMode === 'hybrid' ? 'btn-primary' : 'btn-secondary'}`}
                onClick={() => onReviewModeChange('hybrid')}
              >Hybrid</button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
