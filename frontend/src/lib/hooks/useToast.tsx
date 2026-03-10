import {
  createContext,
  useCallback,
  useContext,
  useState,
  type ReactNode,
} from 'react'
import ToastContainer from '../../components/ToastContainer'

export type ToastType = 'success' | 'error' | 'warning' | 'info' | 'loading'

export interface Toast {
  id: string
  message: string
  type: ToastType
  duration?: number
}

interface ToastContextValue {
  toasts: Toast[]
  showToast: (message: string, type?: ToastType, duration?: number) => string
  hideToast: (id: string) => void
  updateToast: (id: string, updates: Partial<Omit<Toast, 'id'>>) => void
}

const ToastContext = createContext<ToastContextValue | null>(null)

let toastIdCounter = 0

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])

  const showToast = useCallback(
    (message: string, type: ToastType = 'info', duration?: number): string => {
      const id = `toast-${++toastIdCounter}`
      const newToast: Toast = {
        id,
        message,
        type,
        duration: type === 'loading' ? undefined : duration ?? 3000,
      }
      setToasts((prev) => [...prev, newToast])
      return id
    },
    []
  )

  const hideToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }, [])

  const updateToast = useCallback(
    (id: string, updates: Partial<Omit<Toast, 'id'>>) => {
      setToasts((prev) =>
        prev.map((t) => (t.id === id ? { ...t, ...updates } : t))
      )
    },
    []
  )

  return (
    <ToastContext.Provider value={{ toasts, showToast, hideToast, updateToast }}>
      {children}
      <ToastContainer toasts={toasts} onDismiss={hideToast} />
    </ToastContext.Provider>
  )
}

export function useToast() {
  const context = useContext(ToastContext)
  if (!context) {
    throw new Error('useToast must be used within a ToastProvider')
  }
  return context
}

// Convenience hook that returns just showToast for simple cases
export function useShowToast() {
  const { showToast } = useToast()
  return showToast
}
