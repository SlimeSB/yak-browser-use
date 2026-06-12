import React from 'react';
import { useTranslation } from 'react-i18next';

export default function TitleBar() {
  const { t } = useTranslation();
  return (
    <div className="titlebar">
      <span className="titlebar-title">{t('app.title')}</span>
      <div className="titlebar-controls">
        <button className="titlebar-btn" onClick={() => window.electronAPI.windowMinimize()}>─</button>
        <button className="titlebar-btn" onClick={() => window.electronAPI.windowMaximize()}>□</button>
        <button className="titlebar-btn titlebar-close" onClick={() => window.electronAPI.windowClose()}>✕</button>
      </div>
    </div>
  );
}
