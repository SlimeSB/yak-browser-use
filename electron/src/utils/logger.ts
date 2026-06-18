import path from 'path';
import fs from 'fs';

type LogLevel = 'debug' | 'info' | 'warn' | 'error';

type LogEntry = { ts: string; level: string; name: string; msg: string };
type RelayFn = (entry: LogEntry) => void;

const LEVELS: Record<LogLevel, number> = {
  debug: 0,
  info: 1,
  warn: 2,
  error: 3,
};

function _ensureLogDir(): string {
  // Resolve logs/ relative to the project root.
  // In dev: electron/dist/main/ -> three levels up.
  // In production: similar structure.
  const candidates = [
    path.join(__dirname, '..', '..', '..', 'logs'),
    path.join(process.cwd(), 'logs'),
  ];
  for (const dir of candidates) {
    try {
      if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
      // write test
      const testFile = path.join(dir, '.write_test');
      fs.writeFileSync(testFile, '');
      fs.unlinkSync(testFile);
      return dir;
    } catch { /* try next */ }
  }
  return '';
}

function _format(level: LogLevel, name: string, msg: string): string {
  const ts = new Date().toISOString().slice(11, 23).replace('T', ' ');
  const paddedLevel = level.toUpperCase().padEnd(5);
  return `[${ts}] [${paddedLevel}] [${name}] ${msg}`;
}

class Logger {
  private level: LogLevel = 'debug';
  private name: string;
  private logDir: string;
  private fileStream: fs.WriteStream | null = null;
  private static _relayFn: RelayFn | null = null;

  constructor(name: string) {
    this.name = name;
    if (typeof process !== 'undefined' && process.env?.YBU_LOG_LEVEL) {
      const envLevel = process.env.YBU_LOG_LEVEL.toLowerCase() as LogLevel;
      if (envLevel in LEVELS) this.level = envLevel;
    }

    this.logDir = typeof fs !== 'undefined' ? _ensureLogDir() : '';
    if (this.logDir) {
      const p = path.join(this.logDir, 'electron.log');
      try {
        this.fileStream = fs.createWriteStream(p, { flags: 'a', encoding: 'utf-8' });
      } catch { /* no file logging */ }
    }
  }

  static setRelay(fn: RelayFn): void { Logger._relayFn = fn; }
  static clearRelay(): void { Logger._relayFn = null; }

  setLevel(level: LogLevel): void { this.level = level; }

  debug(msg: string, ...args: unknown[]): void { this._log('debug', msg, args); }
  info(msg: string, ...args: unknown[]): void { this._log('info', msg, args); }
  warn(msg: string, ...args: unknown[]): void { this._log('warn', msg, args); }
  error(msg: string, ...args: unknown[]): void { this._log('error', msg, args); }

  close(): void {
    if (this.fileStream) {
      try { this.fileStream.end(); } catch { /* ignore */ }
      this.fileStream = null;
    }
  }

  private _log(level: LogLevel, msg: string, args: unknown[]): void {
    if (LEVELS[level] < LEVELS[this.level]) return;

    const formatted = _format(level, this.name, msg);

    const consoleFn = level === 'error' ? console.error
      : level === 'warn' ? console.warn
      : console.log;

    try {
      if (args.length > 0) consoleFn(formatted, ...args);
      else consoleFn(formatted);
    } catch (error) {
      if ((error as { code?: unknown })?.code === 'EPIPE') return;
      throw error;
    }

    // File output (main process only; renderer lacks fs)
    if (this.fileStream) {
      try {
        this.fileStream.write(formatted + '\n');
      } catch { /* best effort */ }
    }

    // Forward to Python backend console
    if (Logger._relayFn) {
      try {
        Logger._relayFn({
          ts: new Date().toISOString().slice(11, 23).replace('T', ' '),
          level,
          name: this.name,
          msg,
        });
      } catch { /* best effort */ }
    }
  }
}

const instances = new Map<string, Logger>();

export function getLogger(name: string): Logger {
  if (!instances.has(name)) {
    instances.set(name, new Logger(name));
  }
  return instances.get(name)!;
}

export function setLogRelay(fn: RelayFn): void { Logger.setRelay(fn); }
export function clearLogRelay(): void { Logger.clearRelay(); }
