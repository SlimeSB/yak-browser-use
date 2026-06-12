import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';

interface ParamsTabProps {
  credKeys: string[];
  credKey: string;
  onCredKeyChange: (v: string) => void;
  credValue: string;
  onCredValueChange: (v: string) => void;
  onCredSet: () => void;
  onCredDelete: (key: string) => void;
}

export default function ParamsTab({
  credKeys, credKey, onCredKeyChange, credValue, onCredValueChange,
  onCredSet, onCredDelete,
}: ParamsTabProps) {
  const { t } = useTranslation();
  return (
    <div className="cred-layout">
      <div className="cred-toolbar">
        <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)' }}>⚙ {t('paramsTab.title')}</span>
        <div style={{ flex: 1 }} />
        <input className="input" style={{ width: 160 }} placeholder={t('paramsTab.key')} value={credKey} onChange={e => onCredKeyChange(e.target.value)} />
        <input className="input" style={{ width: 200 }} placeholder={t('paramsTab.value')} value={credValue} onChange={e => onCredValueChange(e.target.value)} />
        <button className="btn btn-primary btn-sm" onClick={onCredSet}>{t('paramsTab.add')}</button>
      </div>
      <div className="cred-content">
        {credKeys.length === 0 ? (
          <div style={{ fontSize: 11, color: 'var(--text-muted)', textAlign: 'center', padding: 20 }}>
            {t('paramsTab.noParams')}
          </div>
        ) : (
          credKeys.map(k => (
            <div key={k} className="cred-row">
              <span className="cred-key">{k}</span>
              <span className="cred-val">••••••••</span>
              <button className="btn btn-danger btn-xs" onClick={() => onCredDelete(k)} title={t('paramsTab.delete')}>🗑</button>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
