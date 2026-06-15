import React, { useRef, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import type { EventData } from '../types';

interface EventLogProps {
  events: EventData[];
  maxHeight?: number;
}

const DATA_BLACKLIST = new Set(['_ts', 'session_id', 'timestamp']);

function cleanData(data: Record<string, unknown>): Record<string, unknown> {
  if (!data || typeof data !== 'object') return {};
  return Object.fromEntries(
    Object.entries(data).filter(([k]) => !DATA_BLACKLIST.has(k))
  );
}

function getLineColor(ev: EventData): string {
  if (ev.type === 'chat.tool_end' && ev.data && !ev.data.ok) return 'var(--danger)';
  if (ev.type === 'llm_turn') return 'var(--purple)';
  if (ev.type === 'chat.tool_start') return 'var(--info)';
  if (ev.type === 'chat.tool_end') return 'var(--success)';
  if (ev.type === 'step_error') return 'var(--danger)';
  return 'var(--text-muted)';
}

export default function EventLog({ events, maxHeight }: EventLogProps) {
  const { t } = useTranslation();
  const logRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [events]);

  const formatTime = (ts: string) => {
    try {
      const d = new Date(ts);
      return d.toTimeString().split(' ')[0];
    } catch { return ts; }
  };

  return (
    <div className="log-terminal" ref={logRef} style={maxHeight ? { maxHeight, overflow: 'auto' } : { flex: 1 }}>
      {events.length === 0 && <div style={{ color: 'var(--text-muted)' }}>{t('eventLog.noEvents')}</div>}
      {events.map((ev, i) => {
        const timeStr = ev.timestamp ? formatTime(ev.timestamp) : '';
        const color = getLineColor(ev);
        const json = JSON.stringify(cleanData(ev.data), null, 2);
        return (
          <div key={i} className="log-entry">
            <span className="log-entry-header" style={{ color }}>
              [{timeStr}] {ev.type}
            </span>
            <pre className="log-entry-body">{json}</pre>
          </div>
        );
      })}
    </div>
  );
}
