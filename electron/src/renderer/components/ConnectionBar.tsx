import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';

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
  const { t } = useTranslation();
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
        {connected ? t('connection.connected') : t('connection.disconnected')}
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
            <span className="conn-status-text">{t('connection.mode')}:</span>
            <div className="mode-switch">
              <label className={connectMode === 'user' ? 'active' : ''}>
                <input type="radio" checked={connectMode === 'user'} onChange={() => onModeChange('user')} />
                <span className="radio-dot" /> {t('connection.userBrowser')}
              </label>
              <label className={connectMode === 'isolated' ? 'active' : ''}>
                <input type="radio" checked={connectMode === 'isolated'} onChange={() => onModeChange('isolated')} />
                <span className="radio-dot" /> {t('connection.isolatedBrowser')}
              </label>
            </div>
          </div>

          {connectMode === 'user' ? (
            <div className="conn-segment">
              <button className="btn btn-primary btn-sm" onClick={() => onConnect('user')}>
                {t('connection.connectToChrome')}
              </button>
              <span className="conn-status-text">{t('connection.autoDiscover')}</span>
            </div>
          ) : (
            <div className="conn-segment">
              <div className="profile-select">
                <span className="conn-status-text">{t('connection.profile')}</span>
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
                      placeholder="Enter name and press Enter"
                      className="input-sm"
                    />
                    <button className="btn btn-secondary btn-sm" onClick={() => handleCreateConfirm(newProfileName)}>{t('connection.ok')}</button>
                    <button className="btn btn-secondary btn-sm" onClick={() => { setShowNewProfileInput(false); setNewProfileName(''); }}>{t('connection.cancel')}</button>
                  </span>
                ) : (
                  <button className="btn btn-secondary btn-sm" onClick={handleNewProfile}>{t('connection.newConnection')}</button>
                )}
              </div>
              <button className="btn btn-primary btn-sm" onClick={() => onConnect('isolated', selectedProfile)}>
                {t('connection.startConnect')}
              </button>
            </div>
          )}
        </>
      )}

      {connected && (
        <div className="conn-actions">
          <button className="btn btn-danger btn-sm" onClick={onDisconnect}>{t('connection.disconnect')}</button>
        </div>
      )}
    </div>
  );
}
