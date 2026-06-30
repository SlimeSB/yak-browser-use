import React, { useEffect, useRef } from 'react';
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

export default function App() {
  const { t } = useTranslation();
  const activeTab = useUiStore(s => s.activeTab);
  const setActiveTab = useUiStore(s => s.setActiveTab);
  const loading = usePipelineStore(s => s.loading);
  const pendingReview = usePipelineStore(s => s.pendingReview);
  const initDoneRef = useRef(false);

  // Initial data load
  useEffect(() => {
    if (initDoneRef.current) return;
    initDoneRef.current = true;
    let cancelled = false;
    (async () => {
      const r = await api.listPipelines().catch((e) => {
        console.error('listPipelines failed: %s', String(e));
        return { pipelines: [] };
      });
      if (cancelled) return;
      const chatList = await api.listSessions('__chat__').catch(() => ({ sessions: [] }));
      const chatSessionsList = chatList.sessions || [];
      useChatStore.setState({ chatSessions: chatSessionsList });
      if (r.pipelines && r.pipelines.length > 0) {
        usePipelineStore.setState({ pipelines: r.pipelines });
        const initial = r.pipelines[0].name;
        const list = await api.listSessions(initial).catch(() => ({ sessions: [] }));
        const sessionsList = list.sessions || [];
        if (sessionsList.length > 0) useChatStore.setState({ currentSessionId: sessionsList[0].session_id });
        useChatStore.setState((s) => ({ pipelineSessions: { ...s.pipelineSessions, [initial]: sessionsList } }));
        usePipelineStore.setState({ activePreset: initial });
      } else {
        if (chatSessionsList.length > 0) useChatStore.setState({ currentSessionId: chatSessionsList[0].session_id });
        usePipelineStore.setState({ activePreset: '__chat__' });
      }
    })();
    return () => { cancelled = true; };
  }, []);

  // Load pipeline content when activePreset changes (for editor)
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
          usePipelineStore.setState((s) => ({ pipelineCache: { ...s.pipelineCache, [activePreset]: resp.content }, pipelineEditor: resp.content }));
        }
      }).catch((e) => { console.error('getPipeline failed: %s', String(e)); });
    }
  }, [activePreset, pipelineCache]);

  return (
    <div className="app-container">
      <TitleBar />
      <ConnectionBar />

      <div className="tab-bar">
        <div className={`tab ${activeTab === 'exec' ? 'active' : ''}`} onClick={() => setActiveTab('exec')}>
          <span className="tab-icon">🎯</span> {t('tabs.run')}
          {loading && <span className="tab-badge">{t('tabs.running')}</span>}
        </div>
        <div className={`tab ${activeTab === 'agentmd' ? 'active' : ''}`} onClick={() => setActiveTab('agentmd')}>
          <span className="tab-icon">💬</span> {t('tabs.chat')}
        </div>
        <div className={`tab ${activeTab === 'log' ? 'active' : ''}`} onClick={() => setActiveTab('log')}>
          <span className="tab-icon">📋</span> {t('tabs.log')}
          {pendingReview && <span className="tab-dot" />}
        </div>
        <div className="tab-spacer" />
        <div className={`tab ${activeTab === 'pipelines' ? 'active' : ''}`} onClick={() => setActiveTab('pipelines')}>
          <span className="tab-icon">📦</span> {t('tabs.pipelines')}
        </div>
        <div className={`tab ${activeTab === 'params' ? 'active' : ''}`} onClick={() => setActiveTab('params')}>
          <span className="tab-icon">⚙</span> {t('tabs.params')}
        </div>
        <div className={`tab ${activeTab === 'settings' ? 'active' : ''}`} onClick={() => setActiveTab('settings')}>
          <span className="tab-icon">⚙</span> {t('tabs.settings')}
        </div>
      </div>

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

      <StatusBar />
    </div>
  );
}
