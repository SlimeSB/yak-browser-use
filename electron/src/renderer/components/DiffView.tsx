import React from 'react';

export interface DiffLine {
  type: 'add' | 'del' | 'ctx';
  line: string;
  oldLineNum?: number;
  newLineNum?: number;
  highlights?: Array<{
    start: number;
    end: number;
    type: 'insert' | 'delete';
  }>;
}

interface DiffViewProps {
  lines: DiffLine[];
  maxHeight?: number;
}

function renderHighlightedLine(line: string, highlights?: DiffLine['highlights']): React.ReactNode {
  if (!highlights || highlights.length === 0) {
    return line;
  }

  const parts: React.ReactNode[] = [];
  let lastEnd = 0;

  const sorted = [...highlights].sort((a, b) => a.start - b.start);

  for (const h of sorted) {
    if (h.start > lastEnd) {
      parts.push(line.slice(lastEnd, h.start));
    }
    const text = line.slice(h.start, h.end);
    if (h.type === 'insert') {
      parts.push(<span key={`${h.start}-${h.end}`} className="diff-char-insert">{text}</span>);
    } else {
      parts.push(<span key={`${h.start}-${h.end}`} className="diff-char-delete">{text}</span>);
    }
    lastEnd = h.end;
  }

  if (lastEnd < line.length) {
    parts.push(line.slice(lastEnd));
  }

  return parts;
}

export default function DiffView({ lines, maxHeight }: DiffViewProps) {
  if (!lines || lines.length === 0) {
    return (
      <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)', fontSize: 12 }}>
        No changes
      </div>
    );
  }

  return (
    <div className="diff-body" style={maxHeight ? { maxHeight, overflow: 'auto' } : undefined}>
      {lines.map((dl, i) => (
        <div key={i} className={`diff-line ${dl.type}`}>
          <span className="diff-line-num">
            {dl.type === 'del' ? dl.oldLineNum : dl.newLineNum ?? ''}
          </span>
          <span className="diff-line-content">
            <span className="diff-prefix">{dl.type === 'add' ? '+' : dl.type === 'del' ? '−' : ' '}</span>
            {renderHighlightedLine(dl.line, dl.highlights)}
          </span>
        </div>
      ))}
    </div>
  );
}
