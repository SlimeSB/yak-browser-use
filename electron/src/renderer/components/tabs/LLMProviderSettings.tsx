import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { PresetDefinition } from '../../types';
import * as api from '../../apiClient';

interface ProviderForm {
  model: string;
  api_key: string;
  api_base: string;
}

export function LLMProviderSettings() {
  const { t } = useTranslation();
  const [config, setConfig] = useState<ProviderForm>({ model: '', api_key: '', api_base: '' });
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{ ok: boolean; msg: string } | null>(null);

  const [presets, setPresets] = useState<PresetDefinition[]>([]);
  const [activePresetId, setActivePresetId] = useState<string | null>(null);
  const [presetsError, setPresetsError] = useState('');

  useEffect(() => {
    api.getProviderConfig().then(r => {
      if (r.ok && r.config) {
        const { presets: _, ...rest } = r.config;
        setConfig(prev => ({ ...prev, ...rest } as ProviderForm));
      }
    });
    api.getProviderPresets().then(r => {
      if (r.ok && r.presets) setPresets(r.presets);
      else setPresetsError(r.error || 'Failed to load presets');
    });
  }, []);

  useEffect(() => {
    if (!testResult) return;
    const timer = setTimeout(() => setTestResult(null), 4000);
    return () => clearTimeout(timer);
  }, [testResult]);

  const save = async () => {
    setSaving(true);
    setTestResult(null);
    try {
      await api.setProviderConfig({ ...config });
      setSaved(true);
      setTestResult({ ok: true, msg: t('settingsTab.saved') });
      setTimeout(() => setSaved(false), 2000);
    } catch (e) {
      setTestResult({ ok: false, msg: String(e) });
    }
    setSaving(false);
  };

  const test = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const r = await api.testProvider({ ...config });
      setTestResult(r.ok ? { ok: true, msg: t('settingsTab.testPassed') } : { ok: false, msg: r.error || 'Failed' });
    } catch (e) {
      setTestResult({ ok: false, msg: String(e) });
    }
    setTesting(false);
  };

  const applyPreset = (preset: PresetDefinition) => {
    setConfig(p => ({ ...p, api_base: preset.api_base, model: '' }));
    setActivePresetId(activePresetId === preset.id ? null : preset.id);
  };

  const selectModel = (modelId: string) => setConfig(p => ({ ...p, model: modelId }));
  const updateField = (field: keyof ProviderForm) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setConfig(p => ({ ...p, [field]: e.target.value }));

  const activePreset = presets.find(p => p.id === activePresetId) || null;

  return (
    <div className="set-group">
      <div className="set-group-title">LLM Provider</div>
      <div className="set-row" style={{ flexDirection: 'column', alignItems: 'stretch', gap: 6 }}>
        <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
          {presets.map(p => (
            <button key={p.id}
              className={`btn btn-xs ${activePresetId === p.id ? 'btn-primary' : 'btn-secondary'}`}
              onClick={() => applyPreset(p)}
              title={`API: ${p.api_base}`}
            >{p.name}</button>
          ))}
        </div>
        {presetsError && (
          <div style={{ fontSize: 'var(--fs-sm)', color: '#e81123' }}>{'⚠'}{presetsError}</div>
        )}

        {activePreset && (
          <select className="set-input" value={config.model}
            onChange={e => selectModel(e.target.value)} style={{ marginBottom: 4 }}
          >
            <option value="">-- Select model --</option>
            {activePreset.models.map(m => (
              <option key={m.id} value={m.id}>
                {m.name} ({m.id}){m.context ? ` ⚡${(m.context / 1000).toFixed(0)}K ctx` : ''}
              </option>
            ))}
          </select>
        )}

        <input className="set-input" placeholder="Model (e.g. gpt-4o, deepseek-chat)"
          value={config.model} onChange={updateField('model')} />
        <input className="set-input" type="password" placeholder="API Key"
          value={config.api_key} onChange={updateField('api_key')} />
        <input className="set-input" placeholder="API Base URL (optional)"
          value={config.api_base} onChange={updateField('api_base')} />

        <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
          <button className="btn btn-xs btn-primary" onClick={save} disabled={saving}>
            {saving ? 'Saving...' : saved ? 'Saved ✓' : 'Save'}
          </button>
          <button className="btn btn-xs btn-secondary" onClick={test} disabled={testing}>
            {testing ? 'Testing...' : 'Test'}
          </button>
          {testResult && (
            <span style={{ fontSize: 'var(--fs-sm)', color: testResult.ok ? 'var(--primary)' : '#e81123', marginLeft: 4 }}>
              {testResult.ok ? '✓ ' + testResult.msg : '✗ ' + testResult.msg}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
