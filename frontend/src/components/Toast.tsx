// Legacy Toast component for backwards compatibility
// New code should use useToast hook instead

import { useEffect, useState } from 'react'
import {
  AlertCircle,
  AlertTriangle,
  CheckCircle,
  Info,
  Loader2,
  X,
} from 'lucide-react'

export type ToastType = 'success' | 'error' | 'warning' | 'info' | 'loading'

interface ToastProps {
  message: string
  type: ToastType
  onClose: () => void
  duration?: number
}

const ICONS: Record<ToastType, typeof CheckCircle> = {
  success: CheckCircle,
  error: AlertCircle,
  warning: AlertTriangle,
  info: Info,
  loading: Loader2,
}

export default function Toast({ message, type, onClose, duration = 3000 }: ToastProps) {
  const [isExiting, setIsExiting] = useState(false)

  useEffect(() => {
    if (type === 'loading') return

    const timer = setTimeout(() => {
      setIsExiting(true)
    }, duration)

    return () => clearTimeout(timer)
  }, [type, duration])

  useEffect(() => {
    if (isExiting) {
      const timer = setTimeout(onClose, 200)
      return () => clearTimeout(timer)
    }
  }, [isExiting, onClose])

  const handleDismiss = () => {
    setIsExiting(true)
  }

  const Icon = ICONS[type]

  return (
    <div className="toast-container">
      <div
        className={`toast toast-${type} ${isExiting ? 'toast-exit' : ''}`}
        role="alert"
      >
        <Icon
          size={18}
          className={`toast-icon ${type === 'loading' ? 'toast-icon-spin' : ''}`}
        />
        <span className="toast-message">{message}</span>
        {type !== 'loading' && (
          <button
            className="toast-close"
            onClick={handleDismiss}
            aria-label="Dismiss"
          >
            <X size={14} />
          </button>
        )}
      </div>
    </div>
  )
}
