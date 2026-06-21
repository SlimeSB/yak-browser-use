import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import i18n from '../../i18n';
import type { PresetDefinition } from '../../types';

interface SettingsTabProps {
  reviewMode: string;
  onReviewModeChange: (mode: string) => void;
  chatLayoutReversed: boolean;
  onChatLayoutReversedChange: (v: boolean) => void;
  theme: string;
  onThemeChange: (t: 'dark' | 'light') => void;
  highlightMode: string;
  onHighlightModeChange: (mode: string) => void;
}

interface ProviderForm {
  model: string;
  api_key: string;
  api_base: string;
}

export default function SettingsTab({
  reviewMode, onReviewModeChange,
  chatLayoutReversed, onChatLayoutReversedChange,
  theme, onThemeChange,
  highlightMode, onHighlightModeChange,
}: SettingsTabProps) {
  const { t } = useTranslation();
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
    window.electronAPI.getProviderConfig().then(r => {
      if (r.ok && r.config) {
        const { presets: _, ...rest } = r.config;
        setProviderConfig(prev => ({ ...prev, ...rest } as ProviderForm));
      }
    });
    window.electronAPI.getProviderPresets().then(r => {
      if (r.ok && r.presets) {
        setPresets(r.presets);
      } else {
        setPresetsError(r.error || 'Failed to load presets');
      }
    });
  }, []);

  const handleSaveProvider = async () => {
    setSaving(true);
    const r = await window.electronAPI.setProviderConfig({ ...providerConfig });
    if (r.ok) { setSaved(true); setTimeout(() => setSaved(false), 2000); }
    setSaving(false);
  };

  const handleTest = async () => {
    setTesting(true);
    setTestResult(null);
    const r = await window.electronAPI.testProvider(providerConfig as unknown as Record<string, string>);
    setTestResult(r.ok ? { ok: true, msg: t('settingsTab.testPassed') } : { ok: false, msg: r.error || 'Failed' });
    setTesting(false);
  };

  const applyPreset = (preset: PresetDefinition) => {
    // Set api_base, keep existing api_key, clear model so user picks one
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
                onClick={() => onThemeChange('dark')}
              >{t('settingsTab.dark')}</button>
              <button
                className={`btn btn-xs ${theme === 'light' ? 'btn-primary' : 'btn-secondary'}`}
                onClick={() => onThemeChange('light')}
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
                onClick={() => onReviewModeChange('human')}
              >{t('settingsTab.manual')}</button>
              <button
                className={`btn btn-xs ${reviewMode === 'llm' ? 'btn-primary' : 'btn-secondary'}`}
                onClick={() => onReviewModeChange('llm')}
              >{t('settingsTab.auto')}</button>
              <button
                className={`btn btn-xs ${reviewMode === 'none' ? 'btn-primary' : 'btn-secondary'}`}
                onClick={() => onReviewModeChange('none')}
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
                onClick={() => onChatLayoutReversedChange(false)}
              >{t('settingsTab.chatEditor')}</button>
              <button
                className={`btn btn-xs ${chatLayoutReversed ? 'btn-primary' : 'btn-secondary'}`}
                onClick={() => onChatLayoutReversedChange(true)}
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
                onClick={() => onHighlightModeChange('a11y')}
              >{t('settingsTab.a11y')}</button>
              <button
                className={`btn btn-xs ${highlightMode === 'progressive' ? 'btn-primary' : 'btn-secondary'}`}
                onClick={() => onHighlightModeChange('progressive')}
              >{t('settingsTab.progressive')}</button>
              <button
                className={`btn btn-xs ${highlightMode === 'off' ? 'btn-primary' : 'btn-secondary'}`}
                onClick={() => onHighlightModeChange('off')}
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
              <div style={{ fontSize: 11, color: '#e81123' }}>✗ {presetsError}</div>
            )}

            {/* Model dropdown — shown when a preset is active */}
            {activePreset && (
              <select className="set-input"
                value={providerConfig.model}
                onChange={e => selectModel(e.target.value)}
                style={{ marginBottom: 4 }}
              >
                <option value="">-- Select model --</option>
                {activePreset.models.map(m => (
                  <option key={m.id} value={m.id}>
                    {m.name} ({m.id}){m.context ? ` — ${(m.context / 1000).toFixed(0)}K ctx` : ''}
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
                <span style={{ fontSize: 11, color: testResult.ok ? 'var(--primary)' : '#e81123', marginLeft: 4 }}>
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
