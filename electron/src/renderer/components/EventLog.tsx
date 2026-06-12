import React, { useRef, useEffect } from 'react';
import type { EventData } from '../types';

interface EventLogProps {
  events: EventData[];
  maxHeight?: number;
}

export default function EventLog({ events, maxHeight }: EventLogProps) {
  const logRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [events]);

  const formatTime = (ts: string) => {
    try {
      const d = new Date(ts);
      return d.toTimeString().split(' ')[0];
    } catch (e) { console.debug('formatTime failed:', e); return ts; }
  };

  const getTypeClass = (ev: EventData): string => {
    if (ev.type === 'step_start' || ev.type === 'step_end' || ev.type === 'step_error') {
      if (ev.data?.is_goal || ev.data?.goal_description) return ev.type + '_goal';
      if (ev.data?.browser_ops) return ev.type + '_browser';
    }
    return ev.type;
  };

  const getTypeIcon = (ev: EventData): string => {
    if (ev.type === 'step_start') return ev.data?.is_goal ? '✦' : '●';
    if (ev.type === 'step_end') return ev.data?.is_goal ? '✓' : '✓';
    if (ev.type === 'step_error') return '✗';
    return '';
  };

  return (
    <div className="log-terminal" ref={logRef} style={maxHeight ? { maxHeight, overflow: 'auto' } : { flex: 1 }}>
      {events.length === 0 && <div style={{ color: 'var(--text-muted)' }}>No events yet…</div>}
      {events.map((ev, i) => {
        const cls = getTypeClass(ev);
        const isThought = ev.data?.type === 'thought' || ev.data?.thought;
        const isAction = ev.type === 'step_start' || ev.data?.action || ev.data?.browser_ops;
        const isError = ev.type === 'step_error';
        const isResult = ev.type === 'step_end';

        let lineClass = '';
        if (isError) lineClass = 'error';
        else if (isThought) lineClass = 'thought';
        else if (isAction) lineClass = 'action';
        else if (isResult) lineClass = 'result';

        return (
          <div key={i} className={`step-log-line${lineClass ? ' ' + lineClass : ''}`}>
            <span className="step-log-time">[{ev.timestamp ? formatTime(ev.timestamp) : ''}]</span>
            <span className="step-log-msg">
              <span className={`log-type-${cls}`}>{getTypeIcon(ev)} {ev.type}</span>{' '}
              <span>{ev.node_name}</span>
              {(ev.data?.goal_description || ev.data?.description) ? (
                <span style={{ color: 'var(--text-muted)', marginLeft: 4 }}>
                  — {String(ev.data.goal_description || ev.data.description || '')}
                </span>
              ) : null}
            </span>
          </div>
        );
      })}
    </div>
  );
}
