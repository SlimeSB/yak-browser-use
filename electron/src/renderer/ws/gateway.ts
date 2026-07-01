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
    // Flush any throttled events before reconnecting so stale chunks
    // from the dead connection don't bleed into the new one.
    if (_rafId !== null) {
      cancelAnimationFrame(_rafId);
      _rafId = null;
    }
    for (const ev of Object.values(_pendingStream)) {
      _dispatchImmediate(ev);
    }
    _pendingStream = {};
    _lastSessionId = null;
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
let _pendingStream: Record<string, Record<string, unknown>> = {};
let _rafId: number | null = null;
let _lastSessionId: string | null = null;

function _flushPending() {
  _rafId = null;
  const events = Object.values(_pendingStream);
  // Clear the entire queue — all pending events for the current session are being dispatched now
  _pendingStream = {};
  for (const ev of events) {
    _dispatchImmediate(ev);
  }
}

function _throttle(event: Record<string, unknown>) {
  const sid = event.session_id as string | undefined;
  // If this event belongs to a different session than the one we were
  // tracking, flush the old queue first so stale chunks don't bleed over.
  if (sid && _lastSessionId !== null && sid !== _lastSessionId) {
    _flushPending();
  }
  if (sid) _lastSessionId = sid;
  const key = (event.type as string) + '_' + (event.turn_index ?? '') + '_' + (sid ?? '');
  _pendingStream[key] = event;
  if (_rafId === null) {
    _rafId = requestAnimationFrame(_flushPending);
  }
}

function _dispatchImmediate(event: Record<string, unknown>) {
  const et = event.type as string;

  // NOTE: Event routing is split between dispatch() and this function:
  //   dispatch()  → session.state, chat.stream_start, turn_start (boundary events)
  //   _dispatchImmediate() → chat.*, pipeline.edit, chrome_disconnected, run_end, default
  // The split exists because boundary events need to flush throttled buffers
  // and reset session tracking BEFORE being dispatched.
  // When adding new event types, prefer _dispatchImmediate() unless the event
  // is a session boundary marker.

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
  // New session or new turn: reset session tracking & clear any stale pending chunks
  if (et === 'chat.stream_start' || et === 'session.state' || et === 'turn_start') {
    _lastSessionId = null;
    _pendingStream = {};
  }
  // route session.state => chatStore so it can surface errors
  if (et === 'session.state') {
    useChatStore.getState().handleWsEvent(event);
    return;
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
  if (_rafId !== null) {
    cancelAnimationFrame(_rafId);
    _rafId = null;
  }
  // Flush any remaining throttled events before disconnect
  for (const ev of Object.values(_pendingStream)) {
    _dispatchImmediate(ev);
  }
  _pendingStream = {};
  _lastSessionId = null;
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
