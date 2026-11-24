import type { ReactNode } from 'react'

/** Marco de las pantallas sin sesión (configuración inicial e ingreso). */
export function AuthFrame({ title, intro, children }: { title: string; intro: string; children: ReactNode }) {
  return (
    <div className="grid min-h-full place-items-center px-6 py-12">
      <div className="w-full max-w-md animate-rise">
        <p className="mb-8 flex items-center gap-2 font-semibold tracking-tight">
          <span className="size-2.5 rounded-full bg-lapacho" aria-hidden />
          Contador AI
        </p>
        <div className="ledger-rule mb-6">
          <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
          <p className="mt-1 text-ink-2">{intro}</p>
        </div>
        {children}
      </div>
    </div>
  )
}
