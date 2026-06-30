import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import i18n from '../../i18n';
import type { PresetDefinition } from '../../types';
import * as api from '../../apiClient';
import { useUiStore } from '../../stores/uiStore';
import { useConnectionStore } from '../../stores/connectionStore';
import { usePipelineStore } from '../../stores/pipelineStore';

interface ProviderForm {
  model: string;
  api_key: string;
  api_base: string;
}

export default function SettingsTab() {
  const { t } = useTranslation();
  const theme = useUiStore(s => s.theme);
  const setTheme = useUiStore(s => s.setTheme);
  const chatLayoutReversed = useUiStore(s => s.chatLayoutReversed);
  const setChatLayoutReversed = useUiStore(s => s.setChatLayoutReversed);
  const highlightMode = useConnectionStore(s => s.highlightMode);
  const setHighlightMode = useConnectionStore(s => s.setHighlightMode);
  const reviewMode = usePipelineStore(s => s.reviewMode);
  const setReviewMode = usePipelineStore(s => s.setReviewMode);

  const [providerConfig, setProviderConfig] = useState<ProviderForm>({ model: '', api_key: '', api_base: '' });
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{ ok: boolean; msg: string } | null>(null);

  // Presets from backend
  const [presets, setPresets] = useState<PresetDefinition[]>([]);
  const [activePresetId, setActivePresetId] = useState<string | null>(null);
  const [presetsError, setPresetsError] = useState('');

  useEffect(() => {
    api.getProviderConfig().then(r => {
      if (r.ok && r.config) {
        const { presets: _, ...rest } = r.config;
        setProviderConfig(prev => ({ ...prev, ...rest } as ProviderForm));
      }
    });
    api.getProviderPresets().then(r => {
      if (r.ok && r.presets) {
        setPresets(r.presets);
      } else {
        setPresetsError(r.error || 'Failed to load presets');
      }
    });
  }, []);

  const handleSaveProvider = async () => {
    setSaving(true);
    setTestResult(null);
    try {
      const r = await api.setProviderConfig({ ...providerConfig });
      setSaved(true);
      setTestResult({ ok: true, msg: t('settingsTab.saved') });
      setTimeout(() => setSaved(false), 2000);
    } catch (e) {
      setTestResult({ ok: false, msg: String(e) });
    }
    setSaving(false);
  };

  useEffect(() => {
    if (testResult) {
      const t = setTimeout(() => setTestResult(null), 4000);
      return () => clearTimeout(t);
    }
  }, [testResult]);

  const handleTest = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const { model, api_key, api_base } = providerConfig;
      const r = await api.testProvider({ model, api_key, api_base });
      setTestResult(r.ok ? { ok: true, msg: t('settingsTab.testPassed') } : { ok: false, msg: r.error || 'Failed' });
    } catch (e) {
      setTestResult({ ok: false, msg: String(e) });
    }
    setTesting(false);
  };

  const applyPreset = (preset: PresetDefinition) => {
    setProviderConfig(p => ({ ...p, api_base: preset.api_base, model: '' }));
    setActivePresetId(activePresetId === preset.id ? null : preset.id);
  };

  const selectModel = (modelId: string) => {
    setProviderConfig(p => ({ ...p, model: modelId }));
  };

  const activePreset = presets.find(p => p.id === activePresetId) || null;

  return (
    <div className="set-layout">
      <div className="set-content">
        <div className="set-group">
          <div className="set-group-title">{t('settingsTab.theme')}</div>
          <div className="set-row">
            <div>
              <div className="set-label">{t('settingsTab.colorMode')}</div>
              <div className="set-desc">{theme === 'dark' ? t('settingsTab.darkDesc') : t('settingsTab.lightDesc')}</div>
            </div>
            <div style={{ display: 'flex', gap: 4 }}>
              <button
                className={`btn btn-xs ${theme === 'dark' ? 'btn-primary' : 'btn-secondary'}`}
                onClick={() => setTheme('dark')}
              >{t('settingsTab.dark')}</button>
              <button
                className={`btn btn-xs ${theme === 'light' ? 'btn-primary' : 'btn-secondary'}`}
                onClick={() => setTheme('light')}
              >{t('settingsTab.light')}</button>
            </div>
          </div>
        </div>
        <div className="set-group">
          <div className="set-group-title">{t('settingsTab.language')}</div>
          <div className="set-row">
            <div>
              <div className="set-label">{t('settingsTab.language')}</div>
              <div className="set-desc">{t('settingsTab.langDesc')}</div>
            </div>
            <div style={{ display: 'flex', gap: 4 }}>
              <button
                className={`btn btn-xs ${i18n.language === 'en' ? 'btn-primary' : 'btn-secondary'}`}
                onClick={() => i18n.changeLanguage('en')}
              >English</button>
              <button
                className={`btn btn-xs ${i18n.language === 'zh-CN' ? 'btn-primary' : 'btn-secondary'}`}
                onClick={() => i18n.changeLanguage('zh-CN')}
              >中文</button>
            </div>
          </div>
        </div>
        <div className="set-group">
          <div className="set-group-title">{t('settingsTab.review')}</div>
          <div className="set-row">
            <div>
              <div className="set-label">{t('settingsTab.reviewMode')}</div>
              <div className="set-desc">
                {reviewMode === 'human' ? t('settingsTab.manualDesc') : reviewMode === 'llm' ? t('settingsTab.autoDesc') : t('settingsTab.noneDesc')}
              </div>
            </div>
            <div style={{ display: 'flex', gap: 4 }}>
              <button
                className={`btn btn-xs ${reviewMode === 'human' ? 'btn-primary' : 'btn-secondary'}`}
                onClick={() => setReviewMode('human')}
              >{t('settingsTab.manual')}</button>
              <button
                className={`btn btn-xs ${reviewMode === 'llm' ? 'btn-primary' : 'btn-secondary'}`}
                onClick={() => setReviewMode('llm')}
              >{t('settingsTab.auto')}</button>
              <button
                className={`btn btn-xs ${reviewMode === 'none' ? 'btn-primary' : 'btn-secondary'}`}
                onClick={() => setReviewMode('none')}
              >{t('settingsTab.none')}</button>
            </div>
          </div>
        </div>
        <div className="set-group">
          <div className="set-group-title">{t('settingsTab.chatLayout')}</div>
          <div className="set-row">
            <div>
              <div className="set-label">{t('settingsTab.panelOrder')}</div>
              <div className="set-desc">{chatLayoutReversed ? t('settingsTab.editorFirst') : t('settingsTab.chatFirst')}</div>
            </div>
            <div style={{ display: 'flex', gap: 4 }}>
              <button
                className={`btn btn-xs ${!chatLayoutReversed ? 'btn-primary' : 'btn-secondary'}`}
                onClick={() => setChatLayoutReversed(false)}
              >{t('settingsTab.chatEditor')}</button>
              <button
                className={`btn btn-xs ${chatLayoutReversed ? 'btn-primary' : 'btn-secondary'}`}
                onClick={() => setChatLayoutReversed(true)}
              >{t('settingsTab.editorChat')}</button>
            </div>
          </div>
        </div>
        <div className="set-group">
          <div className="set-group-title">{t('settingsTab.highlight')}</div>
          <div className="set-row">
            <div>
              <div className="set-label">{t('settingsTab.highlightMode')}</div>
              <div className="set-desc">
                {highlightMode === 'a11y' ? t('settingsTab.a11yDesc') : highlightMode === 'progressive' ? t('settingsTab.progressiveDesc') : t('settingsTab.highlightOffDesc')}
              </div>
            </div>
            <div style={{ display: 'flex', gap: 4 }}>
              <button
                className={`btn btn-xs ${highlightMode === 'a11y' ? 'btn-primary' : 'btn-secondary'}`}
                onClick={() => setHighlightMode('a11y')}
              >{t('settingsTab.a11y')}</button>
              <button
                className={`btn btn-xs ${highlightMode === 'progressive' ? 'btn-primary' : 'btn-secondary'}`}
                onClick={() => setHighlightMode('progressive')}
              >{t('settingsTab.progressive')}</button>
              <button
                className={`btn btn-xs ${highlightMode === 'off' ? 'btn-primary' : 'btn-secondary'}`}
                onClick={() => setHighlightMode('off')}
              >{t('settingsTab.highlightOff')}</button>
            </div>
          </div>
        </div>
        <div className="set-group">
          <div className="set-group-title">LLM Provider</div>
          <div className="set-row" style={{ flexDirection: 'column', alignItems: 'stretch', gap: 6 }}>
            {/* Preset buttons */}
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
              <select className="set-input"
                value={providerConfig.model}
                onChange={e => selectModel(e.target.value)}
                style={{ marginBottom: 4 }}
              >
                <option value="">-- Select model --</option>
                {activePreset.models.map(m => (
                  <option key={m.id} value={m.id}>
                    {m.name} ({m.id}){m.context ? ` ⚡${(m.context / 1000).toFixed(0)}K ctx` : ''}
                  </option>
                ))}
              </select>
            )}

            <input className="set-input" placeholder="Model (e.g. gpt-4o, deepseek-chat)" value={providerConfig.model}
              onChange={e => setProviderConfig(p => ({ ...p, model: e.target.value }))} />
            <input className="set-input" type="password" placeholder="API Key" value={providerConfig.api_key}
              onChange={e => setProviderConfig(p => ({ ...p, api_key: e.target.value }))} />
            <input className="set-input" placeholder="API Base URL (optional)" value={providerConfig.api_base}
              onChange={e => setProviderConfig(p => ({ ...p, api_base: e.target.value }))} />
            <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
              <button className="btn btn-xs btn-primary" onClick={handleSaveProvider} disabled={saving}>
                {saving ? 'Saving...' : saved ? 'Saved ✓' : 'Save'}
              </button>
              <button className="btn btn-xs btn-secondary" onClick={handleTest} disabled={testing}>
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
      </div>
    </div>
  );
}
