import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { PipelineMeta, ChatPendingDiff } from '../../types';
import DiffView from '../DiffView';

interface AgentMdTabProps {
  pipelines: PipelineMeta[];
  activePreset: string;
  onPresetChange: (v: string) => void;
  chatMessages: Array<{role: string; content: string}>;
  onChatMessagesChange: (msgs: Array<{role: string; content: string}>) => void;
  chatInput: string;
  onChatInputChange: (v: string) => void;
  chatSending: boolean;
  onChatSend: () => void;
  preset: PipelineMeta | undefined;
  agentMdEditor: string;
  onAgentMdEditorChange: (v: string) => void;
  onTabChange: (tab: string) => void;
  chatPendingDiffs: ChatPendingDiff[];
  onChatDismiss: (index: number) => void;
  onChatRollback: (index: number) => void;
  streamingMsg: string;
}

export default function AgentMdTab({
  pipelines, activePreset, onPresetChange,
  chatMessages, onChatMessagesChange, chatInput, onChatInputChange,
  chatSending, onChatSend, preset, agentMdEditor, onAgentMdEditorChange, onTabChange,
  chatPendingDiffs, onChatDismiss, onChatRollback, streamingMsg,
}: AgentMdTabProps) {
  const { t } = useTranslation();
  const [activeDiffIndex, setActiveDiffIndex] = useState(0);

  const pendingCount = chatPendingDiffs.length;
  const currentDiff = chatPendingDiffs[activeDiffIndex];
  const diffLines = currentDiff ? currentDiff.diff : [];

  return (
    <div className="gen-layout">
      <div className="gen-left">
        <div className="gen-panel" style={{ display: 'flex', flexDirection: 'column' }}>
          <div className="gen-panel-header">
            <span className="gen-panel-title">💬 Chat to modify agent.md</span>
            <select className="select" style={{ fontSize: 10, padding: '2px 6px', width: 140 }}
              value={activePreset}
              onChange={e => {
                onPresetChange(e.target.value);
                onChatMessagesChange([{role: 'system', content: t('agentMdEditor.systemMessage')}]);
                onChatInputChange('');
              }}
            >
              {pipelines.map(p => (
                <option key={p.name} value={p.name}>{p.title}</option>
              ))}
            </select>
          </div>
          <div className="gen-panel-body" style={{ display: 'flex', flexDirection: 'column', gap: 8, flex: 1, overflow: 'hidden' }}>
            <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 6, minHeight: 0 }}>
              {chatMessages.map((msg, i) => (
                <div key={i} className={`gen-chat-msg ${msg.role}`}>
                  {msg.role !== 'user' && (
                    <span className={`gen-chat-avatar ${msg.role === 'system' ? 'system' : 'assistant'}`}>
                      {msg.role === 'system' ? '⚡' : 'A'}
                    </span>
                  )}
                  {msg.role === 'user' && <span className="gen-chat-avatar user">U</span>}
                  <div className={`gen-chat-bubble ${msg.role === 'system' ? 'system' : msg.role === 'user' ? 'user' : 'assistant'}`}
                    style={msg.role === 'system' ? { maxWidth: '100%', textAlign: 'center', fontSize: 11 } : {}}
                  >
                    {msg.content}
                  </div>
                </div>
              ))}
              {chatSending && streamingMsg && (
                <div className="gen-chat-msg assistant">
                  <span className="gen-chat-avatar assistant">A</span>
                  <div className="gen-chat-bubble assistant" style={{ whiteSpace: 'pre-wrap' }}>
                    {streamingMsg}
                  </div>
                </div>
              )}
              {chatSending && !streamingMsg && (
                <div className="gen-chat-msg assistant">
                  <span className="gen-chat-avatar assistant">A</span>
                  <div className="gen-chat-bubble assistant" style={{ color: 'var(--text-muted)' }}>
                    <span className="thinking-dot" /> {t('agentMdEditor.generating')}
                  </div>
                </div>
              )}
            </div>
            {pendingCount > 0 && (
              <div className="chat-review-bar">
                <div className="chat-review-bar-left">
                  <span className="chat-review-dot" />
                  {pendingCount === 1
                    ? 'AI suggested changes, preview diff on the right'
                    : `${pendingCount} changes pending`}
                  {pendingCount > 1 && (
                    <span style={{ display: 'flex', gap: 4, marginLeft: 8 }}>
                      {chatPendingDiffs.map((_, i) => (
                        <span
                          key={i}
                          onClick={() => setActiveDiffIndex(i)}
                          style={{
                            width: 18, height: 18, borderRadius: '50%',
                            display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                            fontSize: 9, cursor: 'pointer',
                            background: i === activeDiffIndex ? 'var(--primary)' : 'var(--bg-hover)',
                            color: i === activeDiffIndex ? '#fff' : 'var(--text-muted)',
                            border: '1px solid var(--border)',
                          }}
                        >
                          {i + 1}
                        </span>
                      ))}
                    </span>
                  )}
                </div>
                <div className="chat-review-bar-right">
                  <button className="btn btn-success btn-sm" onClick={() => onChatDismiss(activeDiffIndex)}>✓ Confirm</button>
                  <button className="btn btn-danger btn-sm" onClick={() => onChatRollback(activeDiffIndex)}>↩ Revert</button>
                </div>
              </div>
            )}
            <div style={{ flexShrink: 0 }}>
              <div style={{ display: 'flex', gap: 6, alignItems: 'flex-end' }}>
                <div style={{ flex: 1, border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', background: 'var(--bg-input)' }}>
                  <textarea className="gen-chat-input" rows={1}
                    value={chatInput}
                    onChange={e => onChatInputChange(e.target.value)}
                    onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); onChatSend(); } }}
                    placeholder={t('agentMdEditor.placeholder')}
                  />
                </div>
                <button className="gen-chat-send" onClick={onChatSend} disabled={chatSending || !chatInput.trim()}>➤</button>
              </div>
              <div style={{ display: 'flex', gap: 4, marginTop: 4, flexWrap: 'wrap' }}>
                <span className="gen-hint" onClick={() => onChatInputChange('Modify step 2 fields')}>Modify step 2 fields</span>
                <span className="gen-hint" onClick={() => onChatInputChange('Add a filter step')}>Add a filter step</span>
                <span className="gen-hint" onClick={() => onChatInputChange('Rename step 3')}>Rename step 3</span>
                <span className="gen-hint" onClick={() => onChatInputChange('Generate from doc')}>Generate from doc</span>
              </div>
            </div>
          </div>
        </div>
      </div>
      <div className="gen-right">
        <div className="gen-panel" style={{ display: 'flex', flexDirection: 'column' }}>
          <div className="gen-panel-header">
            <span className="gen-panel-title">
              📄 agent.md
              {pendingCount > 0 && (
                <span style={{ color: '#f59e0b', fontWeight: 400, fontSize: 10 }}>
                  — {pendingCount} pending
                </span>
              )}
              {pendingCount === 0 && (
                <span style={{ fontWeight: 400, color: 'var(--text-muted)', fontSize: 10 }}>
                  {activePreset ? ` - ${preset?.title || activePreset}` : ''}
                </span>
              )}
            </span>
            <div style={{ display: 'flex', gap: 4 }}>
              <button className="btn btn-secondary btn-xs" onClick={() => {
                if (preset) {
                  window.electronAPI.getPipeline(activePreset).then(resp => {
                    if (resp.agent_md) { onAgentMdEditorChange(resp.agent_md); onChatMessagesChange([{role: 'system', content: 'agent.md refreshed, you can continue chatting to modify.'}]); }
                  }).catch(() => {});
                }
              }}>↩ Refresh</button>
              <button className="btn btn-secondary btn-xs" onClick={() => { navigator.clipboard.writeText(agentMdEditor); }}>📋 Copy</button>
              <button className="btn btn-primary btn-xs" onClick={() => { onTabChange('exec'); }}>▶ {t('preset.run')}</button>
            </div>
          </div>
          <div className="gen-panel-body" style={{ padding: 0, flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
            {pendingCount > 0 ? (
              <DiffView lines={diffLines} />
            ) : (
              <textarea
                className="gen-editor"
                value={agentMdEditor}
                onChange={e => onAgentMdEditorChange(e.target.value)}
                placeholder={t('agentMdEditor.hint')}
                spellCheck={false}
              />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
