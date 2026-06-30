import React from 'react';
import { useTranslation } from 'react-i18next';

export default function TitleBar() {
  const { t } = useTranslation();
  const api = (window as any).electronAPI as Window['electronAPI'] | undefined;
  const isElectron = !!api?.windowMinimize;
  return (
    <div className="titlebar">
      <span className="titlebar-title">{t('app.title')}</span>
      {isElectron && api && (
        <div className="titlebar-controls">
          <button className="titlebar-btn" onClick={() => api.windowMinimize()}>
            <svg width="10" height="10" viewBox="0 0 10 10"><rect x="1" y="4.5" width="8" height="1" fill="currentColor"/></svg>
          </button>
          <button className="titlebar-btn" onClick={() => api.windowMaximize()}>
            <svg width="10" height="10" viewBox="0 0 10 10"><rect x="1.5" y="1.5" width="7" height="7" rx="1" fill="none" stroke="currentColor" strokeWidth="1.2"/></svg>
          </button>
          <button className="titlebar-btn titlebar-close" onClick={() => api.windowClose()}>
            <svg width="10" height="10" viewBox="0 0 10 10"><path d="M1 1l8 8M9 1l-8 8" stroke="currentColor" strokeWidth="1.2"/></svg>
          </button>
        </div>
      )}
    </div>
  );
}
