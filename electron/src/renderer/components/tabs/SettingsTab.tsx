import React from 'react';
import { useTranslation } from 'react-i18next';
import i18n from '../../i18n';
import { useUiStore } from '../../stores/uiStore';
import { useConnectionStore } from '../../stores/connectionStore';
import { usePipelineStore } from '../../stores/pipelineStore';
import { LLMProviderSettings } from './LLMProviderSettings';

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
            <div className="set-segment">
              <button className={`btn btn-sm ${theme === 'dark' ? 'btn-primary' : 'btn-secondary'}`} onClick={() => setTheme('dark')}>{t('settingsTab.dark')}</button>
              <button className={`btn btn-sm ${theme === 'light' ? 'btn-primary' : 'btn-secondary'}`} onClick={() => setTheme('light')}>{t('settingsTab.light')}</button>
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
            <div className="set-segment">
              <button className={`btn btn-sm ${i18n.language === 'en' ? 'btn-primary' : 'btn-secondary'}`} onClick={() => i18n.changeLanguage('en')}>English</button>
              <button className={`btn btn-sm ${i18n.language === 'zh-CN' ? 'btn-primary' : 'btn-secondary'}`} onClick={() => i18n.changeLanguage('zh-CN')}>中文</button>
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
            <div className="set-segment">
              <button className={`btn btn-sm ${reviewMode === 'human' ? 'btn-primary' : 'btn-secondary'}`} onClick={() => setReviewMode('human')}>{t('settingsTab.manual')}</button>
              <button className={`btn btn-sm ${reviewMode === 'llm' ? 'btn-primary' : 'btn-secondary'}`} onClick={() => setReviewMode('llm')}>{t('settingsTab.auto')}</button>
              <button className={`btn btn-sm ${reviewMode === 'none' ? 'btn-primary' : 'btn-secondary'}`} onClick={() => setReviewMode('none')}>{t('settingsTab.none')}</button>
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
            <div className="set-segment">
              <button className={`btn btn-sm ${!chatLayoutReversed ? 'btn-primary' : 'btn-secondary'}`} onClick={() => setChatLayoutReversed(false)}>{t('settingsTab.chatEditor')}</button>
              <button className={`btn btn-sm ${chatLayoutReversed ? 'btn-primary' : 'btn-secondary'}`} onClick={() => setChatLayoutReversed(true)}>{t('settingsTab.editorChat')}</button>
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
            <div className="set-segment">
              <button className={`btn btn-sm ${highlightMode === 'a11y' ? 'btn-primary' : 'btn-secondary'}`} onClick={() => setHighlightMode('a11y')}>{t('settingsTab.a11y')}</button>
              <button className={`btn btn-sm ${highlightMode === 'progressive' ? 'btn-primary' : 'btn-secondary'}`} onClick={() => setHighlightMode('progressive')}>{t('settingsTab.progressive')}</button>
              <button className={`btn btn-sm ${highlightMode === 'off' ? 'btn-primary' : 'btn-secondary'}`} onClick={() => setHighlightMode('off')}>{t('settingsTab.highlightOff')}</button>
            </div>
          </div>
        </div>

        <LLMProviderSettings />
      </div>
    </div>
  );
}
