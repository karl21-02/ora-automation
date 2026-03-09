export default function SettingsPanel() {
  return (
    <div style={{
      flex: 1,
      padding: 24,
      backgroundColor: '#fff',
    }}>
      <h2 style={{
        margin: 0,
        marginBottom: 24,
        fontSize: 20,
        fontWeight: 600,
        color: '#1f2937',
      }}>
        Settings
      </h2>

      <div style={{ marginBottom: 24 }}>
        <h3 style={{
          fontSize: 14,
          fontWeight: 600,
          color: '#374151',
          marginBottom: 12,
        }}>
          Appearance
        </h3>
        <label style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          fontSize: 14,
          color: '#6b7280',
          cursor: 'not-allowed',
        }}>
          <input type="checkbox" disabled style={{ cursor: 'not-allowed' }} />
          <span>Dark mode (coming soon)</span>
        </label>
      </div>

      <div style={{ marginBottom: 24 }}>
        <h3 style={{
          fontSize: 14,
          fontWeight: 600,
          color: '#374151',
          marginBottom: 12,
        }}>
          Notifications
        </h3>
        <label style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          fontSize: 14,
          color: '#6b7280',
          cursor: 'not-allowed',
        }}>
          <input type="checkbox" disabled style={{ cursor: 'not-allowed' }} />
          <span>Email notifications (coming soon)</span>
        </label>
      </div>

      <div>
        <h3 style={{
          fontSize: 14,
          fontWeight: 600,
          color: '#374151',
          marginBottom: 12,
        }}>
          About
        </h3>
        <p style={{ fontSize: 13, color: '#6b7280', margin: 0 }}>
          Ora Automation v0.1.0
        </p>
        <p style={{ fontSize: 12, color: '#9ca3af', marginTop: 4 }}>
          Multi-agent R&D research orchestrator
        </p>
      </div>
    </div>
  )
}
