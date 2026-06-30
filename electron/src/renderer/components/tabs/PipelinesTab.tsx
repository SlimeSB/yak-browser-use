import React from 'react';
import { useTranslation } from 'react-i18next';
import { usePipelineStore } from '../../stores/pipelineStore';
import * as api from '../../apiClient';
import VersionPanel from '../VersionPanel';
import { useUiStore } from '../../stores/uiStore';

export default function PipelinesTab() {
  const { t } = useTranslation();
  const pipelines = usePipelineStore(s => s.pipelines);
  const refreshPipelines = usePipelineStore(s => s.refreshPipelines);
  const setActivePreset = usePipelineStore(s => s.setActivePreset);
  const deletePipeline = usePipelineStore(s => s.deletePipeline);
  const setActiveTab = useUiStore(s => s.setActiveTab);

  return (
    <div className="mgr-layout">
      <div className="mgr-toolbar">
        <span style={{ fontSize: 'var(--fs-sm)', fontWeight: 'var(--fw-semibold)', color: 'var(--text-secondary)' }}>{t('pipelineManager.title')}</span>
        <div style={{ flex: 1 }} />
        <button className="btn btn-sm btn-secondary" onClick={refreshPipelines}>{t('versions.refresh')}</button>
        <button className="btn btn-sm btn-secondary" onClick={() => setActiveTab('agentmd')}>{t('pipelineManager.generateFromDoc')}</button>
      </div>
      <div className="mgr-content">
        {pipelines.length === 0 && (
          <div style={{ fontSize: 'var(--fs-sm)', color: 'var(--text-muted)', textAlign: 'center', padding: 20 }}>
            {t('pipelineManager.noPipelines')}
          </div>
        )}
        {pipelines.map(p => (
          <div key={p.name} className="pipe-card">
            <div className="pipe-card-header">
              <span className="pipe-card-name">{p.title}</span>
              <span className="pipe-card-meta">{p.step_count} steps · {p.name}</span>
            </div>
            <div className="pipe-card-desc">{p.description || t('pipelineManager.noDescription')}</div>
            <div className="pipe-card-actions">
              <button className="btn btn-primary btn-xs" onClick={() => {
                setActivePreset(p.name);
                setActiveTab('exec');
              }}>{t('pipelineManager.run')}</button>
              <button className="btn btn-secondary btn-xs" onClick={() => {
                setActivePreset(p.name);
                setActiveTab('agentmd');
              }}>{t('pipelineManager.edit')}</button>
              <button className="btn btn-secondary btn-xs" onClick={async () => {
                setActivePreset(p.name);
                try {
                  const resp = await api.getPipeline(p.name);
                  if (resp.content) {
                    try { await navigator.clipboard.writeText(resp.content); } catch {
                      const ta = document.createElement('textarea');
                      ta.value = resp.content;
                      ta.style.position = 'fixed'; ta.style.opacity = '0';
                      document.body.appendChild(ta); ta.select();
                      document.execCommand('copy');
                      document.body.removeChild(ta);
                    }
                  }
                } catch (e) { window.alert('Copy failed: ' + String(e)); }
              }}>{t('pipelineManager.copy')}</button>
              <button className="btn btn-danger btn-xs" onClick={() => {
                if (confirm(t('pipelineManager.deleteConfirm', { name: p.title || p.name }))) {
                  deletePipeline(p.name);
                }
              }}>{t('pipelineManager.delete')}</button>
              <VersionPanel pipelineName={p.name} onRefresh={refreshPipelines} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
