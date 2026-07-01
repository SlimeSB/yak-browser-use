import React, { useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useCredentialStore } from '../../stores/credentialStore';

export default function ParamsTab() {
  const { t } = useTranslation();
  const credKeys = useCredentialStore(s => s.credKeys);
  const credKey = useCredentialStore(s => s.credKey);
  const credValue = useCredentialStore(s => s.credValue);
  const setCredKey = useCredentialStore(s => s.setCredKey);
  const setCredValue = useCredentialStore(s => s.setCredValue);
  const addCredential = useCredentialStore(s => s.addCredential);
  const removeCredential = useCredentialStore(s => s.removeCredential);
  const refreshCredentials = useCredentialStore(s => s.refreshCredentials);

  useEffect(() => { refreshCredentials(); }, [refreshCredentials]);

  return (
    <div className="cred-layout">
      <div className="cred-toolbar">
        <span style={{ fontSize: 'var(--fs-sm)', fontWeight: 'var(--fw-semibold)', color: 'var(--text-secondary)' }}>{t('paramsTab.title')}</span>
        <div style={{ flex: 1 }} />
        <input className="input" style={{ width: 160 }} placeholder={t('paramsTab.key')} value={credKey} onChange={e => setCredKey(e.target.value)} />
        <input className="input" style={{ width: 200 }} type="password" placeholder={t('paramsTab.value')} value={credValue} onChange={e => setCredValue(e.target.value)} />
        <button className="btn btn-primary btn-sm" onClick={addCredential}>{t('paramsTab.add')}</button>
      </div>
      <div className="cred-content">
        <div style={{ fontSize: 'var(--fs-sm)', color: 'var(--text-muted)', textAlign: 'center', padding: '4px 20px 8px' }}>
          {t('paramsTab.hint')}
        </div>
        {credKeys.length === 0 ? (
          <div style={{ fontSize: 'var(--fs-sm)', color: 'var(--text-muted)', textAlign: 'center', padding: 20 }}>
            {t('paramsTab.noParams')}
          </div>
        ) : (
          credKeys.map(k => (
            <div key={k} className="cred-row">
              <span className="cred-key">{k}</span>
              <span className="cred-val"> ••••••</span>
              <button className="btn btn-danger btn-xs" onClick={() => removeCredential(k)} title={t('paramsTab.delete')}>✕</button>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
