import React from 'react';
import type { EventData } from '../types';

interface StatusBarProps {
  events: EventData[];
  connected: boolean;
}

export default function StatusBar({ events, connected }: StatusBarProps) {
  const stepDone = events.filter(e => e.type === 'step_end').length;
  const stepTotal = events.filter(e => e.type === 'step_start').length;
  return (
    <div className="status-bar">
      <span>
        <span className={`conn-dot ${connected ? 'ok' : ''}`} />
        {connected ? '已连接' : '未连接'}
      </span>
      <span>{stepTotal > 0 ? `步骤 ${stepDone}/${stepTotal}` : '就绪'}</span>
    </div>
  );
}
