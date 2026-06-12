import { app, BrowserWindow, ipcMain, Menu, dialog } from 'electron';
import { execSync } from 'child_process';
import { PythonBackend } from './backend';
import path from 'path';
import fs from 'fs';
import ExcelJS from 'exceljs';
import { getLogger } from '../utils/logger';

if (process.platform === 'win32') {
  try { execSync('chcp 65001 > nul', { stdio: 'ignore' }); } catch { /* ok */ }
}

const logger = getLogger('main');

let py: PythonBackend;
let mainWindow: BrowserWindow | null = null;

const PORT = 0; // auto-detect from backend

async function createWindow() {
  logger.info('Creating main window');
  mainWindow = new BrowserWindow({
    frame: false,
    width: 1200,
    height: 800,
    title: 'Learning Browser-Use',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  if (process.env.VITE_DEV_SERVER_URL) {
    mainWindow.loadURL(process.env.VITE_DEV_SERVER_URL);
  } else {
    mainWindow.loadFile(path.join(__dirname, '../renderer/index.html'));
  }

  mainWindow.on('closed', () => {
    logger.info('Main window closed');
    mainWindow = null;
  });
}

app.whenReady().then(async () => {
  logger.info('App ready, starting backend...');
  Menu.setApplicationMenu(null);

  py = new PythonBackend();
  let port: number;
  try {
    port = await py.start();
  } catch (e) {
    logger.error('Failed to start backend: %s', (e as Error).message);
    dialog.showErrorBox('启动失败', `无法启动 Python 后端服务:\n${(e as Error).message}\n\n请确认已安装 uv (https://docs.astral.sh/uv/)，并在项目目录下运行 \`uv sync\` 安装依赖。`);
    app.quit();
    return;
  }
  logger.info('Backend started on port %d', port);

  function _url(path: string) { return `http://127.0.0.1:${port}${path}`; }

  async function _apiFetch(path: string, init: RequestInit, label: string): Promise<unknown> {
    try {
      const resp = await fetch(_url(path), init);
      if (!resp.ok) {
        const text = await resp.text().catch(() => '');
        throw new Error(`HTTP ${resp.status}: ${text.slice(0, 200)}`);
      }
      return resp.json();
    } catch (e) {
      logger.error('%s failed: %s', label, (e as Error).message);
      throw e;
    }
  }

  async function _safeFetch(path: string, init: RequestInit = {}): Promise<{ ok: boolean; data?: Record<string, unknown>; error?: string }> {
    try {
      const resp = await fetch(_url(path), init);
      if (!resp.ok) {
        const text = await resp.text().catch(() => '');
        return { ok: false, error: `HTTP ${resp.status}: ${text.slice(0, 200)}` };
      }
      return { ok: true, data: await resp.json() as Record<string, unknown> };
    } catch (e) {
      return { ok: false, error: String(e) };
    }
  }

  ipcMain.handle('api:run', async (_event, { agentMd, params }: { agentMd: string; params?: Record<string, string> }) => {
    logger.debug('IPC: api:run called with %d chars, params=%s', agentMd.length, JSON.stringify(params || {}));
    return _apiFetch('/api/run', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ agent_md: agentMd, params: params || {} }),
    }, 'api:run');
  });

  ipcMain.handle('api:convert', async (_event, document: string) => {
    logger.debug('IPC: api:convert called with %d chars', document.length);
    return _apiFetch('/api/convert', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ document }),
    }, 'api:convert');
  });

  ipcMain.handle('api:chatEdit', async (_event, { agentMd, instruction, history }: { agentMd: string; instruction: string; history?: Record<string, string>[] }) => {
    logger.debug('IPC: api:chatEdit called with instruction=%s', instruction.slice(0, 80));
    return _apiFetch('/api/chat/edit', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ agent_md: agentMd, instruction, history }),
    }, 'api:chatEdit');
  });

  ipcMain.handle('api:status', async () => {
    logger.debug('IPC: api:status called');
    return _apiFetch('/api/status', {}, 'api:status');
  });

  ipcMain.handle('api:chrome-status', async () => {
    logger.debug('IPC: api:chrome-status called');
    return _apiFetch('/api/chrome/status', {}, 'api:chrome-status');
  });

  ipcMain.handle('browser:connect', async (_event, { mode, profileName }: { mode: string; profileName?: string }) => {
    logger.info('IPC: browser:connect mode=%s profile=%s', mode, profileName || 'none');
    try {
      const result = await _safeFetch('/api/chrome/connect', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode, profile_name: profileName }),
      });
      const data = result.data || {};
      if (!result.ok) throw new Error(result.error);
      return {
        success: data.connected ?? false,
        wsUrl: data.ws_url ?? '',
        error: data.error ?? null,
        needsRestart: data.needs_restart ?? false,
        browserName: data.browser_name ?? '',
      };
    } catch (e) {
      logger.error('browser:connect failed: %s', String(e));
      return { success: false, wsUrl: '', error: String(e) };
    }
  });

  ipcMain.handle('browser:restart', async () => {
    logger.info('IPC: browser:restart');
    try {
      const result = await _safeFetch('/api/chrome/restart', { method: 'POST' });
      const data = result.data || {};
      if (!result.ok) throw new Error(result.error);
      return {
        success: data.connected ?? false,
        wsUrl: data.ws_url ?? '',
        error: data.error ?? null,
      };
    } catch (e) {
      logger.error('browser:restart failed: %s', String(e));
      return { success: false, wsUrl: '', error: String(e) };
    }
  });

  ipcMain.handle('browser:disconnect', async () => {
    logger.info('IPC: browser:disconnect');
    try {
      const result = await _safeFetch('/api/chrome/disconnect', { method: 'POST' });
      const data = result.data || {};
      if (!result.ok) throw new Error(result.error);
      return { success: data.disconnected ?? true };
    } catch (e) {
      logger.error('browser:disconnect failed: %s', String(e));
      return { success: false };
    }
  });

  ipcMain.handle('browser:isolated-profiles-list', async () => {
    logger.debug('IPC: browser:isolated-profiles-list');
    const result = await _safeFetch('/api/chrome/isolated-profiles');
    if (!result.ok) return { profiles: ['默认临时目录'] };
    const data = result.data || {};
    return { profiles: data.profiles || [] };
  });

  ipcMain.handle('browser:isolated-profiles-create', async (_event, name: string) => {
    logger.info('IPC: browser:isolated-profiles-create %s', name);
    const result = await _safeFetch(`/api/chrome/isolated-profiles/${encodeURIComponent(name)}`, { method: 'POST' });
    const data = result.data || {};
    return { created: result.ok && data.created, profile_name: data.profile_name || name, error: result.error || undefined };
  });

  ipcMain.handle('dialog:alert', async (_event, message: string) => {
    logger.debug('IPC: dialog:alert');
    if (mainWindow) dialog.showMessageBox(mainWindow, { type: 'info', title: '提示', message, buttons: ['确定'] });
  });

  ipcMain.handle('dialog:open-csv', async () => {
    logger.debug('IPC: dialog:open-csv');
    try {
      const result = await dialog.showOpenDialog(mainWindow!, {
        title: '导入 CSV 文件',
        filters: [{ name: 'CSV 文件', extensions: ['csv'] }],
        properties: ['openFile'],
      });
      if (result.canceled || result.filePaths.length === 0) {
        return { success: false, error: 'cancelled' };
      }
      const filePath = result.filePaths[0];
      const content = fs.readFileSync(filePath, 'utf-8');
      logger.info('CSV imported: %s (%d bytes)', path.basename(filePath), content.length);
      return { success: true, content, filePath };
    } catch (e) {
      logger.error('dialog:open-csv failed: %s', String(e));
      return { success: false, error: String(e) };
    }
  });

  ipcMain.handle('export:csv', async (_event, { data }: { data: unknown }) => {
    logger.debug('IPC: export:csv');
    try {
      const { headers, rows } = _extractTable(data);
      const csvContent = _formatCsv(headers, rows);

      const result = await dialog.showSaveDialog(mainWindow!, {
        title: '导出 CSV',
        defaultPath: `learning-browser-use_${_dateStr()}.csv`,
        filters: [{ name: 'CSV 文件', extensions: ['csv'] }],
      });
      if (result.canceled || !result.filePath) {
        return { success: false, error: 'cancelled' };
      }

      fs.writeFileSync(result.filePath, csvContent, 'utf-8');
      logger.info('CSV exported: %s (%d rows)', result.filePath, rows.length);
      return { success: true, filePath: result.filePath, rows: rows.length };
    } catch (e) {
      logger.error('export:csv failed: %s', String(e));
      return { success: false, error: String(e) };
    }
  });

  ipcMain.handle('export:excel', async (_event, { data }: { data: unknown }) => {
    logger.debug('IPC: export:excel');
    try {
      const result = await dialog.showSaveDialog(mainWindow!, {
        title: '导出 Excel',
        defaultPath: `learning-browser-use_${_dateStr()}.xlsx`,
        filters: [{ name: 'Excel 文件', extensions: ['xlsx'] }],
      });
      if (result.canceled || !result.filePath) {
        return { success: false, error: 'cancelled' };
      }

      const workbook = new ExcelJS.Workbook();
      _buildExcelWorkbook(workbook, data);
      await workbook.xlsx.writeFile(result.filePath);

      logger.info('Excel exported: %s', result.filePath);
      return { success: true, filePath: result.filePath };
    } catch (e) {
      logger.error('export:excel failed: %s', String(e));
      return { success: false, error: String(e) };
    }
  });

  // Version management
  ipcMain.handle('versions:list', async (_event, pipelineName: string) => {
    logger.debug('IPC: versions:list %s', pipelineName);
    return _apiFetch(`/api/versions/${pipelineName}`, {}, 'versions:list');
  });

  ipcMain.handle('versions:get', async (_event, { pipelineName, version }: { pipelineName: string; version: string }) => {
    logger.debug('IPC: versions:get %s v%s', pipelineName, version);
    return _apiFetch(`/api/versions/${pipelineName}/${version}`, {}, 'versions:get');
  });

  ipcMain.handle('versions:relearn', async (_event, pipelineName: string) => {
    logger.debug('IPC: versions:relearn %s', pipelineName);
    return _apiFetch(`/api/versions/${pipelineName}/relearn`, { method: 'POST' }, 'versions:relearn');
  });

  // Window controls
  ipcMain.handle('window:minimize', () => mainWindow?.minimize());
  ipcMain.handle('window:maximize', () => {
    if (mainWindow?.isMaximized()) mainWindow.unmaximize();
    else mainWindow?.maximize();
  });
  ipcMain.handle('window:close', () => mainWindow?.close());

  // Pipeline cancel
  ipcMain.handle('pipeline:cancel', async (_event, { pipelineName, runId }: { pipelineName: string; runId: string }) => {
    logger.info('IPC: pipeline:cancel %s/%s', pipelineName, runId);
    return _apiFetch(`/api/pipeline/${pipelineName}/${runId}/cancel`, { method: 'POST' }, 'pipeline:cancel');
  });

  // Pipeline review
  ipcMain.handle('pipeline:review', async (_event, { threadId, action, reason }: { threadId: string; action: string; reason?: string }) => {
    logger.info('IPC: pipeline:review %s action=%s', threadId, action);
    return _apiFetch(`/api/pipeline/${threadId}/review`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action, reason: reason || '' }),
    }, 'pipeline:review');
  });

  // Credentials
  ipcMain.handle('credentials:list', async () => {
    logger.debug('IPC: credentials:list');
    return _apiFetch('/api/credentials', {}, 'credentials:list');
  });

  ipcMain.handle('credentials:set', async (_event, { key, value }: { key: string; value: string }) => {
    logger.debug('IPC: credentials:set %s', key);
    return _apiFetch(`/api/credentials/${key}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ value }),
    }, 'credentials:set');
  });

  ipcMain.handle('credentials:delete', async (_event, key: string) => {
    logger.debug('IPC: credentials:delete %s', key);
    return _apiFetch(`/api/credentials/${key}`, { method: 'DELETE' }, 'credentials:delete');
  });

  // Backend port for WebSocket
  ipcMain.handle('get:port', () => port);

  // Pipeline discovery
  ipcMain.handle('pipelines:list', async () => {
    logger.debug('IPC: pipelines:list');
    return _apiFetch('/api/pipelines', {}, 'pipelines:list');
  });

  ipcMain.handle('pipelines:get', async (_event, name: string) => {
    logger.debug('IPC: pipelines:get %s', name);
    return _apiFetch(`/api/pipelines/${name}`, {}, 'pipelines:get');
  });

  await createWindow();
}).catch((e) => {
  logger.error('App startup failed: %s', (e as Error).message);
  dialog.showErrorBox('启动失败', `应用启动出错:\n${(e as Error).message}`);
  app.quit();
});

let _stopping = false;

app.on('window-all-closed', () => {
  if (!_stopping) {
    _stopping = true;
    py?.stop();
  }
  if (process.platform !== 'darwin') app.quit();
});

app.on('before-quit', () => {
  if (!_stopping) {
    _stopping = true;
    py?.stop();
  }
});

app.on('will-quit', () => {
  py?.stop();
});

// ── Export helpers ──

function _dateStr(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}_${String(d.getHours()).padStart(2, '0')}-${String(d.getMinutes()).padStart(2, '0')}`;
}

function _extractTable(data: unknown): { headers: string[]; rows: string[][] } {
  if (!data) return { headers: [], rows: [] };

  let rows: Record<string, unknown>[] = [];

  if (Array.isArray(data)) {
    rows = data as Record<string, unknown>[];
  } else if (typeof data === 'object' && data !== null) {
    const obj = data as Record<string, unknown>;
    if (obj.results && Array.isArray(obj.results)) rows = obj.results as Record<string, unknown>[];
    else if (obj.data && Array.isArray(obj.data)) rows = obj.data as Record<string, unknown>[];
    else {
      for (const key of Object.keys(obj)) {
        if (Array.isArray(obj[key])) {
          rows = obj[key] as Record<string, unknown>[];
          break;
        }
      }
    }
  }

  if (rows.length === 0) return { headers: [], rows: [] };

  const headers = Object.keys(rows[0]).slice(0, 30);
  const strRows = rows.map(row => headers.map(h => {
    const v = row[h];
    if (v === null || v === undefined) return '';
    return String(v);
  }));

  return { headers, rows: strRows };
}

function _formatCsv(headers: string[], rows: string[][]): string {
  const escape = (v: string) => {
    if (v.includes(',') || v.includes('"') || v.includes('\n')) {
      return `"${v.replace(/"/g, '""')}"`;
    }
    return v;
  };
  const headerLine = headers.map(escape).join(',');
  const dataLines = rows.map(row => row.map(escape).join(','));
  return '\uFEFF' + [headerLine, ...dataLines].join('\n');
}

function _buildExcelWorkbook(workbook: ExcelJS.Workbook, data: unknown): void {
  if (!data) {
    const sheet = workbook.addWorksheet('导出');
    sheet.addRow(['无数据']);
    return;
  }

  if (Array.isArray(data)) {
    _buildSheet(workbook, '导出', data as Record<string, unknown>[]);
    return;
  }

  if (typeof data !== 'object' || data === null) return;

  const obj = data as Record<string, unknown>;

  const dataKeys = Object.keys(obj).filter(k => {
    const v = obj[k];
    return Array.isArray(v) && (v as unknown[]).length > 0 && typeof (v as unknown[])[0] === 'object';
  });

  if (dataKeys.length > 0) {
    for (const key of dataKeys) {
      _buildSheet(workbook, key, obj[key] as Record<string, unknown>[]);
    }
  } else {
    const sheet = workbook.addWorksheet('数据');
    for (const [k, v] of Object.entries(obj)) {
      sheet.addRow([k, typeof v === 'object' ? JSON.stringify(v) : String(v)]);
    }
  }
}

function _buildSheet(workbook: ExcelJS.Workbook, name: string, rows: Record<string, unknown>[]): void {
  const sheet = workbook.addWorksheet(name.slice(0, 31));
  if (rows.length === 0) return;

  const headers = Object.keys(rows[0]).slice(0, 30);
  const headerRow = sheet.addRow(headers);
  headerRow.font = { bold: true };
  headerRow.fill = {
    type: 'pattern',
    pattern: 'solid',
    fgColor: { argb: 'FFE0E0E0' },
  };

  for (const row of rows) {
    sheet.addRow(headers.map(h => {
      const v = row[h];
      if (v === null || v === undefined) return '';
      if (typeof v === 'number') return v;
      return String(v);
    }));
  }

  for (let i = 1; i <= headers.length; i++) {
    const col = sheet.getColumn(i);
    if (col) col.width = 16;
  }
}
