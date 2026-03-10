import GitHubSettings from './GitHubSettings'
import ProjectListPanel from './ProjectListPanel'
import { useTheme, type Theme } from '../lib/hooks/useTheme'

export default function SettingsPanel() {
  const { theme, setTheme } = useTheme()

  return (
    <div className="settings-panel">
      <h2 className="settings-title">Settings</h2>

      <GitHubSettings />

      <div className="settings-divider" />

      <ProjectListPanel />

      <div className="settings-divider" />

      <div className="settings-section">
        <h3 className="settings-section-title">Appearance</h3>
        <div className="theme-selector">
          {(['light', 'dark', 'system'] as Theme[]).map((t) => (
            <button
              key={t}
              className={`theme-option ${theme === t ? 'active' : ''}`}
              onClick={() => setTheme(t)}
            >
              {t === 'light' && '☀️ Light'}
              {t === 'dark' && '🌙 Dark'}
              {t === 'system' && '💻 System'}
            </button>
          ))}
        </div>
      </div>

      <div className="settings-section">
        <h3 className="settings-section-title">Notifications</h3>
        <label className="settings-checkbox disabled">
          <input type="checkbox" disabled />
          <span>Email notifications (coming soon)</span>
        </label>
      </div>

      <div className="settings-section">
        <h3 className="settings-section-title">About</h3>
        <p className="settings-about-version">Ora Automation v0.1.0</p>
        <p className="settings-about-description">Multi-agent R&D research orchestrator</p>
      </div>
    </div>
  )
}
