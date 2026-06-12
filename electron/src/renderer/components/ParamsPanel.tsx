import React from 'react';

interface ParamsPanelProps {
  schema: Record<string, string>;
  values: Record<string, string>;
  onChange: (key: string, value: string) => void;
}

export default function ParamsPanel({
  schema, values, onChange,
}: ParamsPanelProps) {
  const keys = Object.keys(schema);

  return (
    <div className="panel">
      <div className="panel-title">参数</div>
      <div className="panel-body">
        {keys.length === 0 ? (
          <div style={{ fontSize: 11, color: 'var(--text-muted)', textAlign: 'center', padding: '6px 0' }}>
            无参数
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
