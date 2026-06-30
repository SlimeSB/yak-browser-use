import React, { useEffect, useRef, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import './styles/global.css';
import * as api from './apiClient';
import { useUiStore } from './stores/uiStore';
import { usePipelineStore } from './stores/pipelineStore';
import { useChatStore } from './stores/chatStore';
import TitleBar from './components/TitleBar';
import ConnectionBar from './components/ConnectionBar';
import StatusBar from './components/StatusBar';
import ExecTab from './components/tabs/ExecTab';
import ChatTab from './components/tabs/ChatTab';
import LogTab from './components/tabs/LogTab';
import PipelinesTab from './components/tabs/PipelinesTab';
import ParamsTab from './components/tabs/ParamsTab';
import SettingsTab from './components/tabs/SettingsTab';

const ICONS: Record<string, React.ReactNode> = {
  exec: <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M4 4v16l16-8z"/></svg>,
  agentmd: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>,
  log: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/></svg>,
  pipelines: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>,
  params: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>,
  settings: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>,
};

const TABS = [
  { id: 'exec' as const, icon: 'exec', label: 'tabs.run' },
  { id: 'agentmd' as const, icon: 'agentmd', label: 'tabs.chat' },
  { id: 'log' as const, icon: 'log', label: 'tabs.log' },
  { id: 'pipelines' as const, icon: 'pipelines', label: 'tabs.pipelines' },
  { id: 'params' as const, icon: 'params', label: 'tabs.params' },
  { id: 'settings' as const, icon: 'settings', label: 'tabs.settings' },
];

export default function App() {
  const { t, i18n } = useTranslation();
  const activeTab = useUiStore(s => s.activeTab);
  const setActiveTab = useUiStore(s => s.setActiveTab);
  const loading = usePipelineStore(s => s.loading);
  const pendingReview = usePipelineStore(s => s.pendingReview);
  const sidebarRef = useRef<HTMLElement>(null);

  const measureAndSetWidth = useCallback(() => {
    const el = sidebarRef.current;
    if (!el) return;
    const labels = el.querySelectorAll<HTMLElement>('.sidebar-label');
    let max = 0;
    labels.forEach(l => { max = Math.max(max, l.scrollWidth); });
    if (max > 0) {
      const expandedW = 58 + max + 20;
      el.style.setProperty('--sidebar-expanded', expandedW + 'px');
    }
  }, []);

  useEffect(() => { measureAndSetWidth(); }, [measureAndSetWidth, i18n.language]);

  // ── Initialize app: load pipelines + sessions ───────────────
  useEffect(() => {
    const init = async () => {
      const r = await api.listPipelines().catch(() => ({ pipelines: [] }));
      usePipelineStore.setState({ pipelines: r.pipelines });

      if (r.pipelines.length > 0) {
        const first = r.pipelines[0].name;
        usePipelineStore.getState().setActivePreset(first);
        const sessResp = await api.listSessions(first).catch(() => ({ sessions: [] }));
        const sessions = sessResp.sessions ?? [];
        useChatStore.setState((s) => ({
          pipelineSessions: { ...s.pipelineSessions, [first]: sessions },
          currentSessionId: sessions[0]?.session_id ?? '',
        }));
      } else {
        usePipelineStore.getState().setActivePreset('__chat__');
        const sessResp = await api.listSessions('__chat__').catch(() => ({ sessions: [] }));
        const sessions = sessResp.sessions ?? [];
        useChatStore.setState({
          chatSessions: sessions,
          currentSessionId: sessions[0]?.session_id ?? '',
        });
      }
    };
    init();
  }, []);

  // ── Load pipeline editor content when activePreset changes ──
  const activePreset = usePipelineStore(s => s.activePreset);
  const pipelineCache = usePipelineStore(s => s.pipelineCache);

  useEffect(() => {
    if (!activePreset || activePreset === '__chat__') {
      usePipelineStore.setState({ pipelineEditor: '' });
      return;
    }
    const cached = pipelineCache[activePreset];
    if (cached) {
      usePipelineStore.setState({ pipelineEditor: cached });
    } else {
      api.getPipeline(activePreset).then(resp => {
        if (resp.content) {
          usePipelineStore.setState((s) => ({
            pipelineCache: { ...s.pipelineCache, [activePreset]: resp.content },
            pipelineEditor: resp.content,
          }));
        }
      }).catch((e) => { console.error('getPipeline failed: %s', String(e)); });
    }
  }, [activePreset, pipelineCache]);

  return (
    <div className="app-container">
      <TitleBar />
      <ConnectionBar />

      <div className="app-body">
        <nav className="sidebar" ref={sidebarRef} onMouseEnter={measureAndSetWidth}>
          {TABS.slice(0, 2).map(tab => (
            <button
              key={tab.id}
              className={`sidebar-btn ${activeTab === tab.id ? 'active' : ''}`}
              onClick={() => setActiveTab(tab.id)}
              title={t(tab.label)}
            >
              <span className="sidebar-icon-wrap">{ICONS[tab.icon]}</span>
              <span className="sidebar-label">{t(tab.label)}</span>
              {tab.id === 'exec' && loading && <span className="sidebar-spinner" />}
            </button>
          ))}

          <div className="sidebar-divider" />

          {TABS.slice(2, 4).map(tab => (
            <button
              key={tab.id}
              className={`sidebar-btn ${activeTab === tab.id ? 'active' : ''}`}
              onClick={() => setActiveTab(tab.id)}
              title={t(tab.label)}
            >
              <span className="sidebar-icon-wrap">{ICONS[tab.icon]}</span>
              <span className="sidebar-label">{t(tab.label)}</span>
              {tab.id === 'log' && pendingReview && <span className="sidebar-dot" />}
            </button>
          ))}

          <div className="sidebar-group-gap" />

          {TABS.slice(4).map(tab => (
            <button
              key={tab.id}
              className={`sidebar-btn ${activeTab === tab.id ? 'active' : ''}`}
              onClick={() => setActiveTab(tab.id)}
              title={t(tab.label)}
            >
              <span className="sidebar-icon-wrap">{ICONS[tab.icon]}</span>
              <span className="sidebar-label">{t(tab.label)}</span>
            </button>
          ))}
        </nav>

        <div className="sidebar-content">
          <div className="tab-content" style={{ display: activeTab === 'exec' ? 'flex' : 'none' }}>
            <ExecTab />
          </div>
          <div className="tab-content" style={{ display: activeTab === 'agentmd' ? 'flex' : 'none' }}>
            <ChatTab />
          </div>
          <div className="tab-content" style={{ display: activeTab === 'log' ? 'flex' : 'none' }}>
            <LogTab />
          </div>
          <div className="tab-content" style={{ display: activeTab === 'pipelines' ? 'flex' : 'none' }}>
            <PipelinesTab />
          </div>
          <div className="tab-content" style={{ display: activeTab === 'params' ? 'flex' : 'none' }}>
            <ParamsTab />
          </div>
          <div className="tab-content" style={{ display: activeTab === 'settings' ? 'flex' : 'none' }}>
            <SettingsTab />
          </div>
        </div>
      </div>

      <StatusBar />
    </div>
  );
}
