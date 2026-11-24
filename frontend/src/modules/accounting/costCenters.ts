/** Validación de los centros de costos (sin componentes). */

const CODE = /^[A-Za-z0-9][A-Za-z0-9._-]*$/

/** Validación del formulario de un centro (la misma regla que la API). */
export function centerFormErrors(code: string, name: string): { code?: string; name?: string } {
  const out: { code?: string; name?: string } = {}
  const c = code.trim()
  if (!c) out.code = 'Escribí un código corto, por ejemplo ADM o VEN-01.'
  else if (c.length > 20) out.code = 'Hasta 20 caracteres.'
  else if (!CODE.test(c)) out.code = 'Solo letras, números, guion, guion bajo y punto, sin espacios.'
  if (name.trim().length < 2) out.name = 'Escribí el nombre (al menos 2 caracteres).'
  return out
}
