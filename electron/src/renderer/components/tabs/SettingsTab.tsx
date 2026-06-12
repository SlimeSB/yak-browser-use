import React from 'react';
import { useTranslation } from 'react-i18next';
import i18n from '../../i18n';

interface SettingsTabProps {
  reviewMode: string;
  onReviewModeChange: (mode: string) => void;
  chatLayoutReversed: boolean;
  onChatLayoutReversedChange: (v: boolean) => void;
}

export default function SettingsTab({
  reviewMode, onReviewModeChange,
  chatLayoutReversed, onChatLayoutReversedChange,
}: SettingsTabProps) {
  const { t } = useTranslation();
  return (
    <div className="set-layout">
      <div className="set-content">
        <div className="set-group">
          <div className="set-group-title">{t('settingsTab.review')}</div>
          <div className="set-row">
            <div>
              <div className="set-label">{t('settingsTab.reviewMode')}</div>
              <div className="set-desc">
                {reviewMode === 'human' ? 'Manual approval for all operations' : reviewMode === 'llm' ? 'LLM auto-review' : 'Hybrid mode'}
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
                className={`btn btn-xs ${reviewMode === 'hybrid' ? 'btn-primary' : 'btn-secondary'}`}
                onClick={() => onReviewModeChange('hybrid')}
              >{t('settingsTab.hybrid')}</button>
            </div>
          </div>
        </div>
        <div className="set-group">
          <div className="set-group-title">Chat Layout</div>
          <div className="set-row">
            <div>
              <div className="set-label">Panel order</div>
              <div className="set-desc">{chatLayoutReversed ? 'Editor left, Chat right' : 'Chat left, Editor right'}</div>
            </div>
            <div style={{ display: 'flex', gap: 4 }}>
              <button
                className={`btn btn-xs ${!chatLayoutReversed ? 'btn-primary' : 'btn-secondary'}`}
                onClick={() => onChatLayoutReversedChange(false)}
              >Chat | Editor</button>
              <button
                className={`btn btn-xs ${chatLayoutReversed ? 'btn-primary' : 'btn-secondary'}`}
                onClick={() => onChatLayoutReversedChange(true)}
              >Editor | Chat</button>
            </div>
          </div>
        </div>
        <div className="set-group">
          <div className="set-group-title">{t('settingsTab.language')}</div>
          <div className="set-row">
            <select value={i18n.language} onChange={(e) => i18n.changeLanguage(e.target.value)}>
              <option value="en">English</option>
              <option value="zh">中文</option>
            </select>
          </div>
        </div>
      </div>
    </div>
  );
}
