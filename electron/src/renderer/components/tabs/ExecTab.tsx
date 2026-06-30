import React from 'react';
import { useTranslation } from 'react-i18next';
import { usePipelineStore } from '../../stores/pipelineStore';
import { useConnectionStore } from '../../stores/connectionStore';
import PresetSelectRow from '../PresetSelectRow';
import ParamsPanel from '../ParamsPanel';
import StageList from '../StageList';
import ProgressBar from '../ProgressBar';
import EventLog from '../EventLog';
import ResultTable from '../ResultTable';
import SuggestionsPanel from '../SuggestionsPanel';
import { useUiStore } from '../../stores/uiStore';

export default function ExecTab() {
  const { t } = useTranslation();
  const activePreset = usePipelineStore(s => s.activePreset);
  const pipelines = usePipelineStore(s => s.pipelines);
  const loading = usePipelineStore(s => s.loading);
  const connected = useConnectionStore(s => s.connected);
  const currentRunId = usePipelineStore(s => s.currentRunId);
  const cancelling = usePipelineStore(s => s.cancelling);
  const preset = pipelines.find(p => p.name === activePreset);
  const params = usePipelineStore(s => s.params);
  const pendingReview = usePipelineStore(s => s.pendingReview);
  const stages = preset?.stages ?? [];
  const events = usePipelineStore(s => s.events);
  const result = usePipelineStore(s => s.result);
  const resultErrors = usePipelineStore(s => s.resultErrors);
  const run = usePipelineStore(s => s.run);
  const cancel = usePipelineStore(s => s.cancel);
  const setActivePreset = usePipelineStore(s => s.setActivePreset);
  const setParam = usePipelineStore(s => s.setParam);
  const reviewApprove = usePipelineStore(s => s.reviewApprove);
  const reviewReject = usePipelineStore(s => s.reviewReject);
  const setActiveTab = useUiStore(s => s.setActiveTab);

  return (
    <div className="main-content">
      <div className="left-panel">
        <PresetSelectRow
          activeId={activePreset}
          pipelines={pipelines}
          onSelect={setActivePreset}
          onRun={run}
          loading={loading}
          connected={connected}
        />
        {loading && currentRunId && (
          <div style={{ display: 'flex', gap: 6, justifyContent: 'center' }}>
            <button className="btn btn-danger btn-sm" onClick={cancel} disabled={cancelling}>
              {cancelling ? t('exec.cancel') + '...' : t('exec.cancel')}
            </button>
          </div>
        )}
        <div className="quick-actions">
          <button className="qa-btn" onClick={() => setActiveTab('agentmd')}>{t('exec.generatePipeline')}</button>
          <button className="qa-btn" onClick={() => setActiveTab('params')}>{t('exec.manageParams')}</button>
          <button className="qa-btn" onClick={() => setActiveTab('pipelines')}>{t('pipelineManager.title')}</button>
          <button className="qa-btn" onClick={() => setActiveTab('settings')}>{t('settingsTab.title')}</button>
        </div>
        {preset && (
          <ParamsPanel
            schema={preset.inputs}
            values={params}
            onChange={setParam}
          />
        )}
        {pendingReview && (
          <SuggestionsPanel
            extraOps={pendingReview.extraOps}
            reason={pendingReview.reason}
            guardLayer={pendingReview.guardLayer}
            onApprove={reviewApprove}
            onReject={reviewReject}
          />
        )}
      </div>
      <div className="right-panel">
        <StageList stages={stages} events={events} />
        <ProgressBar events={events} />
        <div className="card">
          <div className="card-title">{t('exec.liveLog')}</div>
          <EventLog events={events} maxHeight={140} />
        </div>
        <ResultTable data={result} errors={resultErrors} />
        {loading && (
          <div className="loading-overlay">
            <div className="spinner" /> {t('exec.processing')}
          </div>
        )}
      </div>
    </div>
  );
}
