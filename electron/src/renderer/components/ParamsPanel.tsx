import React from 'react';
import { useTranslation } from 'react-i18next';

interface ParamsPanelProps {
  schema: Record<string, string>;
  values: Record<string, string>;
  onChange: (key: string, value: string) => void;
}

export default function ParamsPanel({
  schema, values, onChange,
}: ParamsPanelProps) {
  const { t } = useTranslation();
  const keys = Object.keys(schema ?? {});

  return (
    <div className="panel">
      <div className="panel-title">{t('params.title')}</div>
      <div className="panel-body">
        {keys.length === 0 ? (
          <div style={{ fontSize: 'var(--fs-sm)', color: 'var(--text-muted)', textAlign: 'center', padding: '6px 0' }}>
            {t('params.noParams')}
          </div>
        ) : (
          <div className="param-grid">
            {keys.map(key => (
              <div key={key} className="param-row">
                <span className="param-label">{schema[key]}</span>
                <input
                  className="param-input"
                  type="text"
                  value={values[key] ?? ''}
                  onChange={e => onChange(key, e.target.value)}
                />
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
