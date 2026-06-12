import React from 'react';
import { useTranslation } from 'react-i18next';
import type { EventData } from '../types';

interface StatusBarProps {
  events: EventData[];
  connected: boolean;
}

export default function StatusBar({ events, connected }: StatusBarProps) {
  const { t } = useTranslation();
  const stepDone = events.filter(e => e.type === 'step_end').length;
  const stepTotal = events.filter(e => e.type === 'step_start').length;
  return (
    <div className="status-bar">
      <span>
        <span className={`conn-dot ${connected ? 'ok' : ''}`} />
        {connected ? t('connection.connected') : t('connection.disconnected')}
      </span>
      <span>{stepTotal > 0 ? `${t('statusBar.step')} ${stepDone}/${stepTotal}` : t('statusBar.ready')}</span>
    </div>
  );
}
