/** Ayudas de formularios de finanzas (sin componentes). */
import { useState } from 'react'
import { isZeroAmount, parseAmountInput } from '../../lib/money'
import { ApiError } from '../../services/api'

export function errorMessage(error: unknown, fallback = 'Algo falló. Intentá de nuevo.'): string {
  return error instanceof ApiError ? error.message : fallback
}

/** Estado de un formulario con un importe: el texto escrito y su error al validar. */
export function useAmountField(initial = '') {
  const [text, setText] = useState(initial)
  const [error, setError] = useState<string>()
  return {
    text,
    error,
    set: (t: string) => {
      setText(t)
      setError(undefined)
    },
    /** Devuelve el string canónico o `null` (y deja el error a la vista). */
    read: (currency: string, { allowZero = false, positive = false } = {}): string | null => {
      const parsed = parseAmountInput(text, currency)
      if (!parsed.ok) {
        setError(parsed.error)
        return null
      }
      if (!allowZero && isZeroAmount(parsed.value)) {
        setError('El importe no puede ser cero.')
        return null
      }
      if (positive && parsed.value.startsWith('-')) {
        setError('Ingresá el importe sin signo.')
        return null
      }
      return parsed.value
    },
  }
}
