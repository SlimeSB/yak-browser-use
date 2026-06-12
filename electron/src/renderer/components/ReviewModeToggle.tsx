import React from 'react';

interface ReviewModeToggleProps {
  mode: string;
  onChange: (mode: string) => void;
}

export default function ReviewModeToggle({
  mode, onChange,
}: ReviewModeToggleProps) {
  return (
    <div className="card">
      <div className="card-title">Review Mode</div>
      <div className="mode-switch">
        {(['human', 'llm', 'hybrid'] as const).map(m => (
          <label key={m} className={mode === m ? 'active' : ''}>
            <input
              type="radio"
              checked={mode === m}
              onChange={() => onChange(m)}
            />
            <span className="radio-dot" />{' '}
            {m === 'human' ? 'Manual' : m === 'llm' ? 'LLM' : 'Hybrid'}
          </label>
        ))}
      </div>
      <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 4 }}>
        {mode === 'human' && 'All pending operations sent to frontend for manual review'}
        {mode === 'llm' && 'LLM auto-review: pass = inject, reject = blacklist'}
        {mode === 'hybrid' && 'Navigation operations use manual review, rest use LLM review'}
      </div>
    </div>
  );
}
