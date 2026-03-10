import { useEffect, useState } from 'react'
import {
  AlertCircle,
  AlertTriangle,
  CheckCircle,
  Info,
  Loader2,
  X,
} from 'lucide-react'
import type { Toast, ToastType } from '../lib/hooks/useToast'

interface ToastContainerProps {
  toasts: Toast[]
  onDismiss: (id: string) => void
}

export default function ToastContainer({ toasts, onDismiss }: ToastContainerProps) {
  return (
    <div className="toast-container">
      {toasts.map((toast) => (
        <ToastItem key={toast.id} toast={toast} onDismiss={onDismiss} />
      ))}
    </div>
  )
}

interface ToastItemProps {
  toast: Toast
  onDismiss: (id: string) => void
}

const ICONS: Record<ToastType, typeof CheckCircle> = {
  success: CheckCircle,
  error: AlertCircle,
  warning: AlertTriangle,
  info: Info,
  loading: Loader2,
}

function ToastItem({ toast, onDismiss }: ToastItemProps) {
  const [isExiting, setIsExiting] = useState(false)

  useEffect(() => {
    if (!toast.duration) return

    const timer = setTimeout(() => {
      setIsExiting(true)
    }, toast.duration)

    return () => clearTimeout(timer)
  }, [toast.duration])

  useEffect(() => {
    if (isExiting) {
      const timer = setTimeout(() => {
        onDismiss(toast.id)
      }, 200) // Match animation duration
      return () => clearTimeout(timer)
    }
  }, [isExiting, onDismiss, toast.id])

  const handleDismiss = () => {
    setIsExiting(true)
  }

  const Icon = ICONS[toast.type]

  return (
    <div
      className={`toast toast-${toast.type} ${isExiting ? 'toast-exit' : ''}`}
      role="alert"
    >
      <Icon
        size={18}
        className={`toast-icon ${toast.type === 'loading' ? 'toast-icon-spin' : ''}`}
      />
      <span className="toast-message">{toast.message}</span>
      {toast.type !== 'loading' && (
        <button
          className="toast-close"
          onClick={handleDismiss}
          aria-label="Dismiss"
        >
          <X size={14} />
        </button>
      )}
    </div>
  )
}
