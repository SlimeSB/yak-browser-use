import React, { useRef, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import type { EventData } from '../types';

interface EventLogProps {
  events: EventData[];
  maxHeight?: number;
}

const DATA_BLACKLIST = new Set(['_ts', 'session_id', 'timestamp', 'api_key', 'apiKey', 'password', 'secret', 'token', 'auth']);

function cleanData(data: unknown): unknown {
  if (Array.isArray(data)) return data.map(cleanData);
  if (data && typeof data === 'object') {
    const cleaned: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(data as Record<string, unknown>)) {
      if (DATA_BLACKLIST.has(k)) {
        cleaned[k] = '[redacted]';
      } else {
        cleaned[k] = cleanData(v);
      }
    }
    return cleaned;
  }
  return data;
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
    const el = logRef.current;
    if (!el) return;
    const isNearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
    if (isNearBottom) {
      el.scrollTop = el.scrollHeight;
    }
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
