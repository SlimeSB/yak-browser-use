import React from 'react';

interface ResultTableProps {
  data: Record<string, unknown> | null;
  errors: string[] | null;
  columnSchema?: Record<string, string>;
}

export default function ResultTable({ data, errors, columnSchema }: ResultTableProps) {
  const extractRows = (): Record<string, unknown>[] | null => {
    if (!data) return null;
    if (Array.isArray(data)) return data as Record<string, unknown>[];
    if (data.results && Array.isArray(data.results)) return data.results as Record<string, unknown>[];
    if (data.data && Array.isArray(data.data)) return data.data as Record<string, unknown>[];
    for (const key of Object.keys(data)) {
      if (Array.isArray(data[key])) return data[key] as Record<string, unknown>[];
    }
    return null;
  };

  const rows = extractRows();

  if (!data && !errors) return null;

  const columns = rows && rows.length > 0 ? Object.keys(rows[0]).slice(0, 6) : [];

  return (
    <div className="card">
      <div className="card-title">Results</div>
      {errors && errors.length > 0 && (
        <div style={{ color: 'var(--danger)', fontSize: 11, marginBottom: 6 }}>
          {errors.map((e, i) => <div key={i}>{e}</div>)}
        </div>
      )}
      {rows ? (
        <>
          <div style={{ overflowX: 'auto' }}>
            <table className="result-table">
              <thead>
                <tr>
                  {columns.map(col => <th key={col}>{columnSchema?.[col] ?? col}</th>)}
                </tr>
              </thead>
              <tbody>
                {rows.map((row, i) => (
                  <tr key={i}>
                    {columns.map(col => <td key={col}>{String(row[col] ?? '')}</td>)}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="table-footer">
            <span>{rows.length} results</span>
          </div>
        </>
      ) : (
        <div style={{ fontSize: 11, color: 'var(--text-muted)', textAlign: 'center', padding: '8px 0' }}>
          Waiting for results…
        </div>
      )}
    </div>
  );
}
