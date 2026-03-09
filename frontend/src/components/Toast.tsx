import { useEffect } from 'react'
import { CheckCircle, XCircle, Loader2 } from 'lucide-react'

export type ToastType = 'success' | 'error' | 'loading'

interface ToastProps {
  message: string
  type: ToastType
  onClose: () => void
  duration?: number
}

export default function Toast({ message, type, onClose, duration = 2500 }: ToastProps) {
  useEffect(() => {
    if (type === 'loading') return // Don't auto-close loading toasts
    const timer = setTimeout(onClose, duration)
    return () => clearTimeout(timer)
  }, [type, duration, onClose])

  const Icon = type === 'success' ? CheckCircle : type === 'error' ? XCircle : Loader2

  return (
    <div style={containerStyle}>
      <div style={{ ...toastStyle, backgroundColor: bgColors[type] }}>
        <Icon
          size={16}
          color={iconColors[type]}
          style={type === 'loading' ? { animation: 'spin 1s linear infinite' } : undefined}
        />
        <span style={{ color: textColors[type] }}>{message}</span>
      </div>
      <style>{`
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  )
}

const containerStyle: React.CSSProperties = {
  position: 'fixed',
  bottom: 24,
  right: 24,
  zIndex: 1000,
}

const toastStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 8,
  padding: '10px 16px',
  borderRadius: 8,
  boxShadow: '0 4px 12px rgba(0, 0, 0, 0.15)',
  fontSize: 13,
  fontWeight: 500,
}

const bgColors: Record<ToastType, string> = {
  success: '#ecfdf5',
  error: '#fef2f2',
  loading: '#f0f9ff',
}

const iconColors: Record<ToastType, string> = {
  success: '#10b981',
  error: '#ef4444',
  loading: '#3b82f6',
}

const textColors: Record<ToastType, string> = {
  success: '#065f46',
  error: '#991b1b',
  loading: '#1e40af',
}
