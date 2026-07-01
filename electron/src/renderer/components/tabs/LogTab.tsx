import React from 'react';
import { useTranslation } from 'react-i18next';
import { usePipelineStore } from '../../stores/pipelineStore';
import EventLog from '../EventLog';
import ResultTable from '../ResultTable';

export default function LogTab() {
  const { t } = useTranslation();
  const currentRunId = usePipelineStore(s => s.currentRunId);
  const events = usePipelineStore(s => s.events);
  const onClearEvents = usePipelineStore(s => s.clearEvents);
  const result = usePipelineStore(s => s.result);
  const resultErrors = usePipelineStore(s => s.resultErrors);
  const loading = usePipelineStore(s => s.loading);
  const getStepStatus = usePipelineStore(s => s.getStepStatus);
  const activePreset = usePipelineStore(s => s.activePreset);
  const pipelines = usePipelineStore(s => s.pipelines);

  const preset = pipelines.find(p => p.name === activePreset);

  const stageNames = events.filter(e => e.type === 'step_start').map(e => e.node_name);
  // deduplicate while preserving order
  const stepNames = [...new Set(stageNames)];
  const stepStarts = events.filter(e => e.type === 'step_start');
  const stepEnds = events.filter(e => e.type === 'step_end');

  return (
    <div className="log-layout">
      <div className="log-left">
        <div className="log-sidebar-header">
          <span className="log-sidebar-title">{t('log.steps')}</span>
          {currentRunId && <span className="log-sidebar-meta">{currentRunId.slice(0, 8)}</span>}
        </div>
        <div className="log-steps">
          {stepNames.length === 0 ? (
                  <div className="tab-empty-hint">
                    {t('log.noStepData')}
                  </div>
          ) : (
            stepNames.map((name, i) => {
              const status = getStepStatus(name);
              return (
                <div key={i} className={`log-step ${status}`}>
                  <span className={`log-step-icon ${status}`}>
                    {status === 'done' ? '✓' : status === 'error' ? '✗' : status === 'current' ? '●' : `${i + 1}`}
                  </span>
                  <span className="log-step-name">{name}</span>
                  <span className="log-step-time">
                    {status === 'done' ? t('stages.done') : status === 'current' ? t('log.running') : status === 'error' ? t('stages.failed') : '—'}
                  </span>
                </div>
              );
            })
          )}
        </div>
      </div>
        <div className="log-main">
          <div className="tab-toolbar">
            <span className="tab-toolbar-title">{t('exec.liveLog')}</span>
            <span className="tab-toolbar-spacer" />
            <span className="tab-toolbar-meta">{events.length} {t('log.events')}</span>
            <button className="btn btn-secondary btn-sm" onClick={onClearEvents}>{t('log.clear')}</button>
          </div>
        <EventLog events={events} />
      </div>
      <div className="log-right">
        <div className="artifact-section">
          <div className="artifact-title">{t('log.artifacts')}</div>
          {result ? (
            <ResultTable data={result} errors={resultErrors} />
          ) : (
            <div className="artifact-card">
              <div className="artifact-name">{t('log.noArtifacts')}</div>
              <div className="artifact-meta">{t('log.artifactsHint')}</div>
            </div>
          )}
        </div>
        <div className="artifact-section">
          <div className="artifact-title">{t('log.summary')}</div>
          <div className="log-summary-grid">
            <div><span className="log-summary-label">{t('log.step')}s</span> {stepEnds.length}/{stepStarts.length}</div>
            <div><span className="log-summary-label">{t('log.events')}</span> {events.length}</div>
            <div><span className="log-summary-label">{t('log.status')}</span>{' '}
              {loading ? <span className="log-status-running">{t('log.running')}</span>
                : stepStarts.length > 0 ? <span className="log-status-done">{t('log.completed')}</span>
                : <span className="log-status-idle">{t('statusBar.ready')}</span>}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
