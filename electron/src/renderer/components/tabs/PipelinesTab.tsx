import React from 'react';
import { useTranslation } from 'react-i18next';
import type { PipelineMeta } from '../../types';
import VersionPanel from '../VersionPanel';

interface PipelinesTabProps {
  pipelines: PipelineMeta[];
  onRefresh: () => void;
  onSelectPreset: (name: string) => void;
  onTabChange: (tab: string) => void;
}

export default function PipelinesTab({
  pipelines, onRefresh, onSelectPreset, onTabChange,
}: PipelinesTabProps) {
  const { t } = useTranslation();
  return (
    <div className="mgr-layout">
      <div className="mgr-toolbar">
        <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)' }}>📦 {t('pipelineManager.title')}</span>
        <div style={{ flex: 1 }} />
        <button className="btn btn-sm btn-secondary" onClick={onRefresh}>{t('versions.refresh')}</button>
        <button className="btn btn-sm btn-secondary" onClick={() => onTabChange('agentmd')}>📄 Generate from Doc</button>
      </div>
      <div className="mgr-content">
        {pipelines.length === 0 && (
          <div style={{ fontSize: 11, color: 'var(--text-muted)', textAlign: 'center', padding: 20 }}>
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
                onSelectPreset(p.name);
                onTabChange('exec');
              }}>▶ {t('pipelineManager.run')}</button>
              <button className="btn btn-secondary btn-xs" onClick={() => {
                onSelectPreset(p.name);
                onTabChange('agentmd');
              }}>✏ {t('pipelineManager.edit')}</button>
              <button className="btn btn-secondary btn-xs" onClick={() => {
                onSelectPreset(p.name);
                window.electronAPI.getPipeline(p.name).then(resp => {
                  if (resp.agent_md) {
                    navigator.clipboard.writeText(resp.agent_md);
                  }
                }).catch((e) => { console.error('getPipeline failed:', e); });
              }}>📋 Copy</button>
              <VersionPanel pipelineName={p.name} onRefresh={onRefresh} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
