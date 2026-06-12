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
      <div className="card-title">审查模式</div>
      <div className="mode-switch">
        {(['human', 'llm', 'hybrid'] as const).map(m => (
          <label key={m} className={mode === m ? 'active' : ''}>
            <input
              type="radio"
              checked={mode === m}
              onChange={() => onChange(m)}
            />
            <span className="radio-dot" />{' '}
            {m === 'human' ? '人工' : m === 'llm' ? 'LLM' : '混合'}
          </label>
        ))}
      </div>
      <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 4 }}>
        {mode === 'human' && '所有待审查操作推送到前端人工审批'}
        {mode === 'llm' && 'LLM 自动审查，通过即注入，拒绝入黑名单'}
        {mode === 'hybrid' && '导航操作用人工审批，其余LLM审查'}
      </div>
    </div>
  );
}
