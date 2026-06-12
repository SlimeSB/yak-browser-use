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
          <div className="set-group-title">审查</div>
          <div className="set-row">
            <div>
              <div className="set-label">审查模式</div>
              <div className="set-desc">
                {reviewMode === 'human' ? '人工审批所有操作' : reviewMode === 'llm' ? 'LLM 自动审查' : '混合模式'}
              </div>
            </div>
            <div style={{ display: 'flex', gap: 4 }}>
              <button
                className={`btn btn-xs ${reviewMode === 'human' ? 'btn-primary' : 'btn-secondary'}`}
                onClick={() => onReviewModeChange('human')}
              >人工</button>
              <button
                className={`btn btn-xs ${reviewMode === 'llm' ? 'btn-primary' : 'btn-secondary'}`}
                onClick={() => onReviewModeChange('llm')}
              >LLM</button>
              <button
                className={`btn btn-xs ${reviewMode === 'hybrid' ? 'btn-primary' : 'btn-secondary'}`}
                onClick={() => onReviewModeChange('hybrid')}
              >混合</button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
