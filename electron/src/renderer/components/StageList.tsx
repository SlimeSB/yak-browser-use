import React from 'react';
import type { EventData } from '../types';

interface StageListProps {
  stages: string[];
  events: EventData[];
}

export default function StageList({ stages, events }: StageListProps) {
  const getStageStatus = (name: string): 'done' | 'current' | 'pending' | 'error' => {
    const hasStart = events.some(e => e.type === 'step_start' && e.node_name === name);
    const hasEnd = events.some(e => e.type === 'step_end' && e.node_name === name);
    const hasError = events.some(e => e.type === 'step_error' && e.node_name === name);

    if (hasError) return 'error';
    if (hasStart && hasEnd) return 'done';
    if (hasStart && !hasEnd) return 'current';
    return 'pending';
  };

  const stageNames = stages.length > 0 ? stages
    : events.filter(e => e.type === 'step_start').map(e => e.node_name);

  if (stageNames.length === 0) {
    return (
      <div className="card">
        <div className="card-title">Execution Stages</div>
        <div style={{ fontSize: 11, color: 'var(--text-muted)', textAlign: 'center', padding: '8px 0' }}>
          Waiting to start…
        </div>
      </div>
    );
  }

  return (
    <div className="card">
      <div className="card-title">Execution Stages</div>
      <div className="stage-list">
        {stageNames.map((name, i) => {
          const status = getStageStatus(name);
          return (
            <div key={i} className="stage-item" style={{
              background: status === 'current' ? 'var(--primary-bg)' : status === 'done' ? 'var(--success-bg)' : 'transparent',
            }}>
              <span className={`stage-icon ${status}`}>
                {status === 'done' ? '✓' : status === 'error' ? '✗' : status === 'current' ? '●' : `${i + 1}`}
              </span>
              <span className="stage-name" style={{
                fontWeight: status === 'current' ? 600 : 400,
              }}>{name}</span>
              <span className="stage-status-text">
                {status === 'done' ? 'Done' : status === 'current' ? 'Running…' : status === 'error' ? 'Failed' : 'Pending'}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
