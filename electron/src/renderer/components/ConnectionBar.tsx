import React, { useState } from 'react';

interface ConnectionBarProps {
  connected: boolean; wsUrl: string;
  connectMode: 'user' | 'isolated'; selectedProfile: string;
  connectionError: string | null;
  onConnect: (mode: 'user' | 'isolated', profile?: string) => void;
  onDisconnect: () => void;
  onModeChange: (mode: 'user' | 'isolated') => void;
  onProfileChange: (profile: string) => void;
  profiles: string[];
  onCreateProfile: (name: string) => Promise<void>;
}

export default function ConnectionBar({
  connected, wsUrl, connectMode, selectedProfile, connectionError, onConnect, onDisconnect,
  onModeChange, onProfileChange, profiles, onCreateProfile,
}: ConnectionBarProps) {
  const [showNewProfileInput, setShowNewProfileInput] = useState(false);
  const [newProfileName, setNewProfileName] = useState('');

  const handleNewProfile = async () => {
    setShowNewProfileInput(true);
    setNewProfileName('');
  };

  const handleCreateConfirm = async (name: string) => {
    const trimmed = name.trim();
    if (!trimmed) return;
    await onCreateProfile(trimmed);
    setShowNewProfileInput(false);
    setNewProfileName('');
  };

  const handleCreateKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') handleCreateConfirm(newProfileName);
    if (e.key === 'Escape') { setShowNewProfileInput(false); setNewProfileName(''); }
  };

  return (
    <div className="connection-bar">
      <span className={`conn-dot ${connected ? 'ok' : ''}`} />
      <span className="conn-label">
        {connected ? '已连接' : '未连接'}
      </span>
      {connected && wsUrl && (
        <span className="conn-url" title={wsUrl}>{wsUrl}</span>
      )}

      {!connected && (
        <>
          {connectionError && (
            <span className="conn-error" title={connectionError}>{connectionError}</span>
          )}

          <div className="conn-segment">
            <span className="conn-status-text">模式:</span>
            <div className="mode-switch">
              <label className={connectMode === 'user' ? 'active' : ''}>
                <input type="radio" checked={connectMode === 'user'} onChange={() => onModeChange('user')} />
                <span className="radio-dot" /> 用户浏览器
              </label>
              <label className={connectMode === 'isolated' ? 'active' : ''}>
                <input type="radio" checked={connectMode === 'isolated'} onChange={() => onModeChange('isolated')} />
                <span className="radio-dot" /> 隔离浏览器
              </label>
            </div>
          </div>

          {connectMode === 'user' ? (
            <div className="conn-segment">
              <button className="btn btn-primary btn-sm" onClick={() => onConnect('user')}>
                连接到 Chrome
              </button>
              <span className="conn-status-text">自动发现正在运行的 Chrome</span>
            </div>
          ) : (
            <div className="conn-segment">
              <div className="profile-select">
                <span className="conn-status-text">Profile:</span>
                <select value={selectedProfile} onChange={e => onProfileChange(e.target.value)}>
                  {profiles.map(p => (
                    <option key={p} value={p}>{p}</option>
                  ))}
                </select>
                {showNewProfileInput ? (
                  <span className="new-profile-input">
                    <input
                      autoFocus
                      value={newProfileName}
                      onChange={e => setNewProfileName(e.target.value)}
                      onKeyDown={handleCreateKeyDown}
                      placeholder="输入名称后回车"
                      className="input-sm"
                    />
                    <button className="btn btn-secondary btn-sm" onClick={() => handleCreateConfirm(newProfileName)}>确定</button>
                    <button className="btn btn-secondary btn-sm" onClick={() => { setShowNewProfileInput(false); setNewProfileName(''); }}>取消</button>
                  </span>
                ) : (
                  <button className="btn btn-secondary btn-sm" onClick={handleNewProfile}>新建</button>
                )}
              </div>
              <button className="btn btn-primary btn-sm" onClick={() => onConnect('isolated', selectedProfile)}>
                启动并连接
              </button>
            </div>
          )}
        </>
      )}

      {connected && (
        <div className="conn-actions">
          <button className="btn btn-danger btn-sm" onClick={onDisconnect}>断开</button>
        </div>
      )}
    </div>
  );
}
