import { ChildProcess, spawn, execSync } from 'child_process';
import { join } from 'path';
import { tmpdir } from 'os';
import { readdirSync, readFileSync, writeFileSync, unlinkSync, existsSync } from 'fs';
import http from 'http';
import { getLogger } from '../utils/logger';

const logger = getLogger('backend');

function _pidFile(ownerPid: number): string {
  return join(tmpdir(), `ybu-backend.${ownerPid}.pid`);
}

function _isProcessAlive(pid: number): boolean {
  try {
    if (process.platform === 'win32') {
      const result = execSync(`tasklist /FI "PID eq ${pid}" /NH`, { encoding: 'utf-8', stdio: 'pipe' });
      return result.includes(String(pid));
    } else {
      process.kill(pid, 0);
      return true;
    }
  } catch {
    return false;
  }
}

function _killProcess(pid: number): void {
  try {
    if (process.platform === 'win32') {
      execSync(`taskkill /PID ${pid} /F /T 2>nul`, { stdio: 'ignore' });
    } else {
      process.kill(pid, 'SIGKILL');
    }
  } catch { /* already dead */ }
}

function _cleanupZombieBackends(): void {
  try {
    const files = readdirSync(tmpdir()).filter(f => /^ybu-backend\.\d+\.pid$/.test(f));
    for (const file of files) {
      const match = file.match(/^ybu-backend\.(\d+)\.pid$/);
      if (!match) continue;
      const ownerPid = parseInt(match[1], 10);
      if (!_isProcessAlive(ownerPid)) {
        const pidPath = join(tmpdir(), file);
        try {
          const pythonPid = parseInt(readFileSync(pidPath, 'utf-8').trim(), 10);
          if (pythonPid) {
            _killProcess(pythonPid);
            logger.info('Cleaned up zombie Python backend (pid=%d)', pythonPid);
          }
        } catch { /* file corrupted or missing */ }
        try { unlinkSync(pidPath); } catch { /* ok */ }
      }
    }
  } catch { /* tmpdir not readable */ }
}

export class PythonBackend {
  private process: ChildProcess | null = null;
  private port: number = 0;
  private _pidFile: string | null = null;

  async start(): Promise<number> {
    const serverDir = join(__dirname, '../../../backend');
    logger.info('Starting Python backend...');

    _cleanupZombieBackends();

    let spawnError: Error | null = null;
    let exitCode: number | null = null;
    const stderrChunks: string[] = [];

    this.process = spawn(
      'uv',
      ['run', 'python', '-m', 'yak_browser_use', 'serve', '--port', '0'],
      {
        cwd: serverDir,
        stdio: ['pipe', 'pipe', 'pipe'],
        env: { ...process.env, PYTHONUTF8: '1', PYTHONIOENCODING: 'utf-8' },
        windowsHide: true,
      },
    );

    this.process.on('error', (err) => {
      spawnError = err;
      logger.error('Failed to spawn Python backend: %s', err.message);
    });

    if (this.process.pid) {
      this._pidFile = _pidFile(process.pid);
      try { writeFileSync(this._pidFile, String(this.process.pid), 'utf-8'); } catch { /* ok */ }
    }

    this.process.on('exit', (code) => {
      if (!this.port) exitCode = code ?? -1;
      if (this._pidFile) {
        try { if (existsSync(this._pidFile)) unlinkSync(this._pidFile); } catch { /* ok */ }
        this._pidFile = null;
      }
    });

    this.process.stdout?.on('data', (data: Buffer) => {
      const text = data.toString();
      const match = text.match(/running on http:\/\/127\.0\.0\.1:(\d+)/);
      if (match) {
        this.port = parseInt(match[1], 10);
      }
    });

    this.process.stderr?.setEncoding('utf-8');
    this.process.stderr?.on('data', (data: string) => {
      const text = data;
      stderrChunks.push(text);
      logger.debug('[stderr] ' + text.trimEnd());
      const uvicornMatch = text.match(/Uvicorn running on http:\/\/127\.0\.0\.1:(\d+)/);
      const cliMatch = text.match(/ybu FastAPI running on http:\/\/127\.0\.0\.1:(\d+)/);
      const match = uvicornMatch || cliMatch;
      if (match) {
        this.port = parseInt(match[1], 10);
        logger.info('Python backend started on port %d', this.port);
      }
    });

    try {
      await this._waitForReady(30_000);
      return this.port;
    } catch (e) {
      if (spawnError) {
        logger.error('Backend failed to start (spawn error): %s', (spawnError as Error).message);
        throw spawnError;
      }
      if (exitCode !== null) {
        const tail = stderrChunks.join('').trim().split('\n').slice(-5).join('\n');
        const msg = `Python backend exited with code ${exitCode}${tail ? '\nLast stderr:\n' + tail : ''}`;
        logger.error('Backend failed to start: %s', msg);
        throw new Error(msg);
      }
      logger.error('Backend failed to start: %s', (e as Error).message);
      throw e;
    }
  }

  private async _waitForReady(timeout: number): Promise<void> {
    const start = Date.now();
    while (Date.now() - start < timeout) {
      if (this.port) {
        try {
          await new Promise<void>((resolve, reject) => {
            const req = http.get(`http://127.0.0.1:${this.port}/api/status`, (res) => {
              if (res.statusCode === 200) resolve();
              else reject();
            });
            req.on('error', reject);
            req.setTimeout(1000, () => { req.destroy(); reject(); });
          });
          return;
        } catch {
          // retry
        }
      }
      if (this.process && this.process.exitCode !== null) {
        throw new Error(`Python backend exited with code ${this.process.exitCode}`);
      }
      await new Promise((r) => setTimeout(r, 500));
    }
    throw new Error('Backend failed to start within timeout');
  }

  private _stopping = false;

  stop(force = false): void {
    if (this._stopping || !this.process) return;
    this._stopping = true;
    const pid = this.process.pid;
    logger.info('Stopping Python backend (pid=%d, force=%s)', pid, force);

    if (pid) {
      try {
        if (process.platform === 'win32') {
          execSync(`taskkill /PID ${pid}${force ? ' /F /T' : ''} 2>nul`, { stdio: 'ignore' });
        } else {
          process.kill(pid, force ? 'SIGKILL' : 'SIGTERM');
        }
      } catch { /* already dead */ }
    }

    if (!force) {
      setTimeout(() => {
        if (this.process && !this.process.killed && this.process.pid) {
          logger.warn(
            'Python backend still alive after graceful shutdown, force killing (pid=%d)',
            this.process.pid,
          );
          _killProcess(this.process.pid);
        }
      }, 3000);
    }

    if (this._pidFile) {
      try { if (existsSync(this._pidFile)) unlinkSync(this._pidFile); } catch { /* ok */ }
      this._pidFile = null;
    }
  }

  getPort(): number {
    return this.port;
  }
}
