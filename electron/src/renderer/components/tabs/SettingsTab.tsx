import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import i18n from '../../i18n';

interface SettingsTabProps {
  reviewMode: string;
  onReviewModeChange: (mode: string) => void;
  chatLayoutReversed: boolean;
  onChatLayoutReversedChange: (v: boolean) => void;
  theme: string;
  onThemeChange: (t: 'dark' | 'light') => void;
}

export default function SettingsTab({
  reviewMode, onReviewModeChange,
  chatLayoutReversed, onChatLayoutReversedChange,
  theme, onThemeChange,
}: SettingsTabProps) {
  const { t } = useTranslation();
  const [providerConfig, setProviderConfig] = useState({ model: '', api_key: '', api_base: '' });
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{ ok: boolean; msg: string } | null>(null);
  const [presets, setPresets] = useState<Record<string, { model: string; api_key: string; api_base: string }>>({});
  const [activePreset, setActivePreset] = useState('');

  useEffect(() => {
    window.electronAPI.getProviderConfig().then(r => {
      if (r.ok && r.config) {
        const { presets: p, ...rest } = r.config;
        setProviderConfig(prev => ({ ...prev, ...rest }));
        if (p) setPresets(p);
      }
    });
  }, []);

  const applyPreset = (name: string) => {
    const p = presets[name];
    if (p) { setProviderConfig(p); setActivePreset(name); }
  };

  const handleSaveProvider = async () => {
    setSaving(true);
    const r = await window.electronAPI.setProviderConfig({ ...providerConfig, presets });
    if (r.ok) { setSaved(true); setTimeout(() => setSaved(false), 2000); }
    setSaving(false);
  };

  const handleTest = async () => {
    setTesting(true);
    setTestResult(null);
    const r = await window.electronAPI.testProvider(providerConfig);
    setTestResult(r.ok ? { ok: true, msg: r.response || 'OK' } : { ok: false, msg: r.error || 'Failed' });
    setTesting(false);
  };

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
                className={`btn btn-xs ${i18n.language === 'zh' ? 'btn-primary' : 'btn-secondary'}`}
                onClick={() => i18n.changeLanguage('zh')}
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
          <div className="set-group-title">LLM Provider</div>
          <div className="set-row" style={{ flexDirection: 'column', alignItems: 'stretch', gap: 6 }}>
            {Object.keys(presets).length > 0 && (
              <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                {Object.keys(presets).map(name => (
                  <button key={name}
                    className={`btn btn-xs ${activePreset === name ? 'btn-primary' : 'btn-secondary'}`}
                    onClick={() => applyPreset(name)}
                  >{name}</button>
                ))}
              </div>
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
