import { useState } from 'react'
import { googleAuth, type AuthUser } from '../lib/api'

// Google OAuth Client ID for desktop app
const GOOGLE_CLIENT_ID = '379646863345-ik2tkrja7qn19eqj1uia56711vl6nn58.apps.googleusercontent.com'

// Dynamic import for Tauri shell plugin (only available in Tauri app)
async function openInBrowser(url: string): Promise<void> {
  try {
    // Try Tauri shell plugin first (desktop app)
    const { open } = await import('@tauri-apps/plugin-shell')
    await open(url)
  } catch {
    // Fallback to window.open for web (won't work for OOB flow, but handles gracefully)
    window.open(url, '_blank')
  }
}

interface LoginScreenProps {
  onLogin: (user: AuthUser) => void
}

export default function LoginScreen({ onLogin }: LoginScreenProps) {
  const [code, setCode] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showCodeInput, setShowCodeInput] = useState(false)

  const handleGoogleLogin = async () => {
    // Open Google OAuth in browser
    const redirectUri = 'urn:ietf:wg:oauth:2.0:oob'
    const scope = encodeURIComponent('email profile')
    const authUrl = `https://accounts.google.com/o/oauth2/v2/auth?client_id=${GOOGLE_CLIENT_ID}&redirect_uri=${redirectUri}&response_type=code&scope=${scope}&access_type=offline`

    try {
      await openInBrowser(authUrl)
      setShowCodeInput(true)
      setError(null)
    } catch (err) {
      setError('Failed to open browser. Please try again.')
      console.error('Failed to open browser:', err)
    }
  }

  const handleSubmitCode = async () => {
    if (!code.trim()) {
      setError('Please enter the authorization code')
      return
    }

    setLoading(true)
    setError(null)

    try {
      const response = await googleAuth(code.trim())
      onLogin(response.user)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Login failed'
      setError(message)
      console.error('Login error:', err)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      height: '100vh',
      backgroundColor: '#fafafa',
      fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
    }}>
      <div style={{
        backgroundColor: 'white',
        borderRadius: 16,
        padding: 48,
        boxShadow: '0 4px 24px rgba(0, 0, 0, 0.08)',
        maxWidth: 400,
        width: '100%',
        textAlign: 'center',
      }}>
        {/* Logo / Title */}
        <div style={{ marginBottom: 32 }}>
          <h1 style={{
            fontSize: 32,
            fontWeight: 700,
            color: '#1f2937',
            margin: 0,
            marginBottom: 8,
          }}>
            Mimir
          </h1>
          <p style={{
            fontSize: 14,
            color: '#6b7280',
            margin: 0,
          }}>
            Multi-agent R&D Research Orchestrator
          </p>
        </div>

        {!showCodeInput ? (
          // Step 1: Google Login Button
          <>
            <button
              onClick={handleGoogleLogin}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: 12,
                width: '100%',
                padding: '14px 24px',
                backgroundColor: 'white',
                border: '1px solid #e5e7eb',
                borderRadius: 8,
                fontSize: 15,
                fontWeight: 500,
                color: '#374151',
                cursor: 'pointer',
                transition: 'all 0.15s ease',
              }}
              onMouseOver={(e) => {
                e.currentTarget.style.backgroundColor = '#f9fafb'
                e.currentTarget.style.borderColor = '#d1d5db'
              }}
              onMouseOut={(e) => {
                e.currentTarget.style.backgroundColor = 'white'
                e.currentTarget.style.borderColor = '#e5e7eb'
              }}
            >
              <svg width="20" height="20" viewBox="0 0 24 24">
                <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
                <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
                <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
                <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
              </svg>
              Continue with Google
            </button>
          </>
        ) : (
          // Step 2: Enter authorization code
          <>
            <p style={{
              fontSize: 14,
              color: '#6b7280',
              marginBottom: 16,
              lineHeight: 1.6,
            }}>
              A browser window has opened. After signing in with Google, copy the authorization code and paste it below.
            </p>

            <input
              type="text"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              placeholder="Paste authorization code here"
              style={{
                width: '100%',
                padding: '12px 16px',
                fontSize: 14,
                border: '1px solid #e5e7eb',
                borderRadius: 8,
                marginBottom: 16,
                outline: 'none',
                boxSizing: 'border-box',
              }}
              onFocus={(e) => e.currentTarget.style.borderColor = '#3b82f6'}
              onBlur={(e) => e.currentTarget.style.borderColor = '#e5e7eb'}
              onKeyDown={(e) => e.key === 'Enter' && handleSubmitCode()}
              autoFocus
            />

            <button
              onClick={handleSubmitCode}
              disabled={loading}
              style={{
                width: '100%',
                padding: '14px 24px',
                backgroundColor: loading ? '#9ca3af' : '#3b82f6',
                border: 'none',
                borderRadius: 8,
                fontSize: 15,
                fontWeight: 500,
                color: 'white',
                cursor: loading ? 'not-allowed' : 'pointer',
                transition: 'background-color 0.15s ease',
                marginBottom: 12,
              }}
              onMouseOver={(e) => !loading && (e.currentTarget.style.backgroundColor = '#2563eb')}
              onMouseOut={(e) => !loading && (e.currentTarget.style.backgroundColor = '#3b82f6')}
            >
              {loading ? 'Signing in...' : 'Sign In'}
            </button>

            <button
              onClick={() => {
                setShowCodeInput(false)
                setCode('')
                setError(null)
              }}
              style={{
                background: 'none',
                border: 'none',
                fontSize: 13,
                color: '#6b7280',
                cursor: 'pointer',
                padding: 8,
              }}
            >
              Back
            </button>
          </>
        )}

        {error && (
          <p style={{
            color: '#ef4444',
            fontSize: 13,
            marginTop: 16,
            marginBottom: 0,
          }}>
            {error}
          </p>
        )}
      </div>

      <p style={{
        fontSize: 12,
        color: '#9ca3af',
        marginTop: 24,
      }}>
        Mímisbrunnr - The Well of Wisdom
      </p>
    </div>
  )
}
