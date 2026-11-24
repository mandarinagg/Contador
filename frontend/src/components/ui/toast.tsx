import { CheckCircle2, CircleAlert } from 'lucide-react'
import { createContext, type ReactNode, use, useCallback, useState } from 'react'

interface Toast {
  id: number
  tone: 'ok' | 'bad'
  message: string
}

const ToastContext = createContext<((tone: Toast['tone'], message: string) => void) | null>(null)

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])
  const push = useCallback((tone: Toast['tone'], message: string) => {
    const id = Date.now() + Math.random()
    setToasts((t) => [...t, { id, tone, message }])
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 4500)
  }, [])

  return (
    <ToastContext value={push}>
      {children}
      <div aria-live="polite" className="pointer-events-none fixed right-5 bottom-5 z-50 flex flex-col gap-2">
        {toasts.map((t) => (
          <div
            key={t.id}
            className="pointer-events-auto flex max-w-sm animate-rise items-start gap-2.5 rounded-md bg-surface px-3.5 py-3 shadow-(--shadow-float)"
          >
            {t.tone === 'ok' ? (
              <CheckCircle2 size={16} className="mt-0.5 shrink-0 text-ledger" />
            ) : (
              <CircleAlert size={16} className="mt-0.5 shrink-0 text-debit" />
            )}
            <p>{t.message}</p>
          </div>
        ))}
      </div>
    </ToastContext>
  )
}

export function useToast() {
  const push = use(ToastContext)
  if (!push) throw new Error('useToast fuera de ToastProvider')
  return push
}
