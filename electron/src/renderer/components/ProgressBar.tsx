import React from 'react';
import type { EventData } from '../types';

interface ProgressBarProps {
  events: EventData[];
}

export default function ProgressBar({ events }: ProgressBarProps) {
  const stepStarts = events.filter(e => e.type === 'step_start');
  const stepEnds = events.filter(e => e.type === 'step_end');
  const stepErrors = events.filter(e => e.type === 'step_error');
  const total = stepStarts.length;
  const done = stepEnds.length;

  if (total === 0) {
    return (
      <div className="card">
        <div className="card-title">Progress</div>
        <div style={{ fontSize: 11, color: 'var(--text-muted)', textAlign: 'center', padding: '8px 0' }}>
          Waiting to start…
        </div>
      </div>
    );
  }

  const pct = Math.round((done / total) * 100);

  return (
    <div className="card">
      <div className="card-title">Progress</div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <div className="progress-bar">
          <div className={`progress-bar-fill ${stepErrors.length > 0 ? 'error' : ''}`} style={{ width: `${pct}%` }} />
        </div>
        <span style={{ fontSize: 11, color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>
          {done}/{total} {pct}%
        </span>
      </div>
    </div>
  );
}
