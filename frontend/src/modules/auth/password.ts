/** Política de contraseñas: espejo de `identity/schemas.py` (el backend es quien decide). */
export const PASSWORD_HINT = 'Mínimo 12 caracteres, con al menos tres de: minúsculas, mayúsculas, números y símbolos.'

export function passwordProblem(pw: string): string | undefined {
  if (pw.length < 12) return 'Tiene que tener al menos 12 caracteres.'
  if (pw.trim() !== pw) return 'No puede empezar ni terminar con espacios.'
  const classes = [/[a-z]/, /[A-Z]/, /\d/, /[^a-zA-Z0-9]/].filter((r) => r.test(pw)).length
  if (classes < 3) return 'Usá al menos tres de: minúsculas, mayúsculas, números y símbolos.'
  return undefined
}
