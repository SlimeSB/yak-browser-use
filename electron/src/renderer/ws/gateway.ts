import * as api from '../apiClient';
import { useConnectionStore } from '../stores/connectionStore';
import { usePipelineStore } from '../stores/pipelineStore';
import { useChatStore } from '../stores/chatStore';

let _ws: WebSocket | null = null;
let _reconnectTimer: ReturnType<typeof setTimeout>;
let _reconnectScheduled = false;
let _stopped = false;

function scheduleReconnect(delay: number) {
  if (_reconnectScheduled) return;
  _reconnectScheduled = true;
  clearTimeout(_reconnectTimer);
  _reconnectTimer = setTimeout(() => {
    _reconnectScheduled = false;
    connect();
  }, delay);
}

async function connect() {
  if (_stopped) return;
  try {
    _ws = await api.createWebSocket('/ws/events');
    if (_stopped) { _ws.close(); return; }
    _ws.onmessage = (ev) => {
      try {
        dispatch(JSON.parse(ev.data));
      } catch (e) { console.log('WebSocket message parse error: %s', String(e)); }
    };
    _ws.onclose = () => { if (!_stopped) scheduleReconnect(3000); };
    _ws.onerror = () => { if (!_stopped) scheduleReconnect(5000); };
  } catch (e) {
    console.log('WebSocket connect failed: %s', String(e));
    if (!_stopped) scheduleReconnect(5000);
  }
}

const _THROTTLED_TYPES = new Set(['chat.text_chunk', 'chat.think_chunk']);
const _pendingStream: Record<string, Record<string, unknown>> = {};
let _rafId: number | null = null;

function _flushPending() {
  _rafId = null;
  const events = Object.values(_pendingStream);
  for (const ev of events) {
    delete _pendingStream[ev.type as string + '_' + (ev.turn_index ?? '')];
  }
  for (const ev of events) {
    _dispatchImmediate(ev);
  }
}

function _throttle(event: Record<string, unknown>) {
  const key = (event.type as string) + '_' + (event.turn_index ?? '');
  _pendingStream[key] = event;
  if (_rafId === null) {
    _rafId = requestAnimationFrame(_flushPending);
  }
}

function _dispatchImmediate(event: Record<string, unknown>) {
  const et = event.type as string;

  // Step 1: chat.* events
  if (et.startsWith('chat.')) {
    useChatStore.getState().handleWsEvent(event);
    return;
  }

  // Step 1.5: pipeline.edit → chatStore (handles PendingEdit tracking)
  if (et === 'pipeline.edit') {
    useChatStore.getState().handleWsEvent(event);
    return;
  }

  // Step 2: chrome_disconnected → connectionStore
  if (et === 'chrome_disconnected') {
    useConnectionStore.getState().handleBrowserDisconnect();
    return;
  }

  // Step 3: run_end → pipelineStore
  if (et === 'run_end') {
    usePipelineStore.getState().handleRunEnd();
    return;
  }

  // Step 4: default → pipelineStore.addEvent
  usePipelineStore.getState().addEvent(
    et,
    (event.step || event.pipeline || '') as string,
    event,
  );
}

function dispatch(event: Record<string, unknown>) {
  const et = event.type as string;
  // Throttle high-frequency streaming events to once per frame
  if (_THROTTLED_TYPES.has(et)) {
    _throttle(event);
    return;
  }
  // Ensure any pending streaming events are flushed before state-changing events
  if (_rafId !== null) {
    cancelAnimationFrame(_rafId);
    _rafId = null;
    _flushPending();
  }
  _dispatchImmediate(event);
}

export function initGateway() {
  _stopped = false;
  connect();
}

export function destroyGateway() {
  _stopped = true;
  clearTimeout(_reconnectTimer);
  _reconnectScheduled = false;
  if (_ws) {
    _ws.onclose = null;
    _ws.onerror = null;
    _ws.close();
    _ws = null;
  }
}

// HMR cleanup
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const _importMeta = import.meta as any;
if (_importMeta.hot) {
  _importMeta.hot.dispose(() => {
    destroyGateway();
  });
}
