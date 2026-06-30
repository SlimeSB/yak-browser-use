import React from 'react';
import { useTranslation } from 'react-i18next';
import type { PipelineMeta } from '../../types';
import * as api from '../../apiClient';
import VersionPanel from '../VersionPanel';

interface PipelinesTabProps {
  pipelines: PipelineMeta[];
  onRefresh: () => void;
  onSelectPreset: (name: string) => void;
  onTabChange: (tab: string) => void;
  onDeletePipeline: (name: string) => void;
}

export default function PipelinesTab({
  pipelines, onRefresh, onSelectPreset, onTabChange, onDeletePipeline,
}: PipelinesTabProps) {
  const { t } = useTranslation();
  return (
    <div className="mgr-layout">
      <div className="mgr-toolbar">
        <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)' }}>📦 {t('pipelineManager.title')}</span>
        <div style={{ flex: 1 }} />
        <button className="btn btn-sm btn-secondary" onClick={onRefresh}>{t('versions.refresh')}</button>
        <button className="btn btn-sm btn-secondary" onClick={() => onTabChange('agentmd')}>📄 {t('pipelineManager.generateFromDoc')}</button>
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
              <button className="btn btn-secondary btn-xs" onClick={async () => {
                onSelectPreset(p.name);
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
              }}>📋 {t('pipelineManager.copy')}</button>
              <button className="btn btn-danger btn-xs" onClick={() => {
                if (confirm(t('pipelineManager.deleteConfirm', { name: p.title || p.name }))) {
                  onDeletePipeline(p.name);
                }
              }}>🗑 {t('pipelineManager.delete')}</button>
              <VersionPanel pipelineName={p.name} onRefresh={onRefresh} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
