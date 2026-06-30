import React from 'react';
import { useTranslation } from 'react-i18next';
import { usePipelineStore } from '../stores/pipelineStore';
import { useConnectionStore } from '../stores/connectionStore';

export default function StatusBar() {
  const { t } = useTranslation();
  const events = usePipelineStore(s => s.events);
  const connected = useConnectionStore(s => s.connected);
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
