import React, { useState, useCallback, useEffect } from 'react';
import type { VersionInfo } from '../types';

interface VersionPanelProps {
  pipelineName: string;
  onRefresh: () => void;
}

export default function VersionPanel({ pipelineName, onRefresh }: VersionPanelProps) {
  const [versions, setVersions] = useState<VersionInfo[]>([]);
  const [viewing, setViewing] = useState<{ version: string; content: string } | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    if (!pipelineName) return;
    try {
      const resp = await window.electronAPI.listVersions(pipelineName);
      setVersions(resp.versions || []);
    } catch (e) { console.error('listVersions failed:', e); }
  }, [pipelineName]);

  useEffect(() => { load(); }, [load]);

  const handleView = useCallback(async (version: string) => {
    setViewing(null);
    try {
      const resp = await window.electronAPI.getVersion(pipelineName, version);
      setViewing({ version: resp.version, content: resp.content });
    } catch (e) { console.error('getVersion failed:', e); }
  }, [pipelineName]);

  const handleRelearn = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await window.electronAPI.relearn(pipelineName);
      if (resp.deleted) {
        await load();
        onRefresh();
      }
    } catch (e) { console.error('relearn failed:', e); }
    setLoading(false);
  }, [pipelineName, load, onRefresh]);

  if (!pipelineName || versions.length === 0) return null;

  return (
    <div className="card">
      <div className="card-title">
        学习版本
        <button className="btn btn-sm btn-secondary" onClick={load} style={{ marginLeft: 8 }}>刷新</button>
      </div>
      <div className="version-list">
        {versions.map(v => (
          <div key={v.version} className="version-item">
            <span className="version-num">v{v.version}</span>
            <span className="version-date">{v.created_at?.slice(0, 19) || ''}</span>
            <span className="version-size">{(v.size / 1024).toFixed(1)}KB</span>
            <button className="btn btn-xs btn-secondary" onClick={() => handleView(v.version)}>查看</button>
          </div>
        ))}
      </div>
      <div style={{ marginTop: 6 }}>
        <button className="btn btn-danger btn-sm" onClick={handleRelearn} disabled={loading}>
          {loading ? '处理中…' : '重学'}
        </button>
        <span style={{ fontSize: 11, color: 'var(--text-muted)', marginLeft: 8 }}>
          删除最新学习版本
        </span>
      </div>
      {viewing && (
        <div className="version-preview" style={{ marginTop: 8, maxHeight: 200, overflow: 'auto', background: 'var(--bg-subtle)', padding: 8, borderRadius: 4 }}>
          <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4 }}>查看 v{viewing.version}</div>
          <pre style={{ fontSize: 10, whiteSpace: 'pre-wrap', margin: 0 }}>{viewing.content.slice(0, 2000)}{viewing.content.length > 2000 ? '...' : ''}</pre>
          <button className="btn btn-sm btn-secondary" onClick={() => setViewing(null)} style={{ marginTop: 4 }}>关闭</button>
        </div>
      )}
    </div>
  );
}
