type LogLevel = 'debug' | 'info' | 'warn' | 'error';

const LEVELS: Record<LogLevel, number> = {
  debug: 0,
  info: 1,
  warn: 2,
  error: 3,
};

class Logger {
  private level: LogLevel = 'debug';
  private name: string;

  constructor(name: string) {
    this.name = name;
    if (typeof process !== 'undefined' && process.env?.YBU_LOG_LEVEL) {
      const envLevel = process.env.YBU_LOG_LEVEL.toLowerCase() as LogLevel;
      if (envLevel in LEVELS) this.level = envLevel;
    }
  }

  setLevel(level: LogLevel): void { this.level = level; }

  debug(msg: string, ...args: unknown[]): void { this._log('debug', msg, args); }
  info(msg: string, ...args: unknown[]): void { this._log('info', msg, args); }
  warn(msg: string, ...args: unknown[]): void { this._log('warn', msg, args); }
  error(msg: string, ...args: unknown[]): void { this._log('error', msg, args); }

  private _log(level: LogLevel, msg: string, args: unknown[]): void {
    if (LEVELS[level] < LEVELS[this.level]) return;
    const ts = new Date().toISOString().slice(11, 23);
    const paddedLevel = level.toUpperCase().padEnd(5);
    const prefix = `[${ts}] [${paddedLevel}] [${this.name}]`;

    const consoleFn = level === 'error' ? console.error
      : level === 'warn' ? console.warn
      : console.log;

    try {
      if (args.length > 0) {
        consoleFn(`${prefix} ${msg}`, ...args);
      } else {
        consoleFn(`${prefix} ${msg}`);
      }
    } catch (error) {
      if ((error as { code?: unknown })?.code === 'EPIPE') return;
      throw error;
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
