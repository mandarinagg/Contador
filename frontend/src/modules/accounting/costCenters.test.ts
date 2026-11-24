import { describe, expect, it } from 'vitest'
import { centerFormErrors } from './costCenters'

describe('centro de costos', () => {
  it('código corto sin espacios y nombre', () => {
    expect(centerFormErrors('ADM', 'Administración')).toEqual({})
    expect(centerFormErrors('VEN-01.a_b', 'Ventas')).toEqual({})
    expect(centerFormErrors('', 'x').code).toBeDefined()
    expect(centerFormErrors('A B', 'Ventas').code).toMatch(/sin espacios/)
    expect(centerFormErrors('A'.repeat(21), 'Ventas').code).toMatch(/20/)
    expect(centerFormErrors('ADM', ' ').name).toBeDefined()
  })
})
