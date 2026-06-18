import http from 'http';

type LogEntry = { ts: string; level: string; name: string; msg: string };

let _relayUrl = '';
let _buffer: LogEntry[] = [];
let _flushTimer: ReturnType<typeof setInterval> | null = null;
let _enabled = false;

export function initLogRelay(backendPort: number): void {
  if (_enabled) return;
  _relayUrl = `http://127.0.0.1:${backendPort}/api/logs/forward`;
  _enabled = true;
  _flushTimer = setInterval(flushLogBuffer, 500);
}

export function stopLogRelay(): void {
  _enabled = false;
  if (_flushTimer) { clearInterval(_flushTimer); _flushTimer = null; }
  flushLogBuffer();
  _buffer = [];
}

export function relayLog(entry: LogEntry): void {
  if (!_enabled) return;
  _buffer.push(entry);
  // Flush immediately for errors
  if (entry.level === 'error') flushLogBuffer();
}

function flushLogBuffer(): void {
  if (_buffer.length === 0) return;
  const batch = _buffer.splice(0);
  const payload = JSON.stringify({ entries: batch });

  const options: http.RequestOptions = {
    hostname: '127.0.0.1',
    port: parseInt(_relayUrl.split(':')[2]?.split('/')[0] || '0', 10),
    path: '/api/logs/forward',
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Content-Length': Buffer.byteLength(payload),
    },
    timeout: 2000,
  };

  const req = http.request(options);
  req.on('error', () => { /* best effort, drop silently */ });
  req.write(payload);
  req.end();
}
