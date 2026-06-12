import React from 'react';
import type { PipelineMeta } from '../types';

interface PresetSelectRowProps {
  activeId: string;
  pipelines: PipelineMeta[];
  onSelect: (id: string) => void;
  onRun: () => void;
  loading: boolean;
  connected: boolean;
}

export default function PresetSelectRow({
  activeId, pipelines, onSelect, onRun, loading, connected,
}: PresetSelectRowProps) {
  const preset = pipelines.find(p => p.name === activeId);
  return (
    <div className="panel">
      <div className="panel-title">
        <span>管线</span>
        <span style={{ fontWeight: 400, textTransform: 'none', letterSpacing: 0 }}>
          {pipelines.length} 可用
        </span>
      </div>
      <div className="panel-body" style={{ paddingBottom: 10 }}>
        <div className="preset-select-row">
          <select
            className="preset-select"
            value={activeId}
            onChange={e => onSelect(e.target.value)}
            disabled={loading}
          >
            {pipelines.length === 0 && <option value="">无可用管线</option>}
            {pipelines.map(t => (
              <option key={t.name} value={t.name}>{t.title}</option>
            ))}
          </select>
          <button
            className="btn btn-primary"
            onClick={onRun}
            disabled={loading || !connected}
          >
            {loading ? '执行中…' : '▶ 执行'}
          </button>
        </div>
        {preset && (
          <div className="pipeline-meta">
            <span>{preset.step_count} 步骤</span>
            {preset.description && <span>{preset.description}</span>}
          </div>
        )}
      </div>
    </div>
  );
}
