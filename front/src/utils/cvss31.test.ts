import { describe, expect, it } from 'vitest'

import { calculateEnvironmental, defaultEnvironmentalMetrics } from './cvss31'


const base = 'CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H'

describe('CVSS v3.1 environmental preview', () => {
  it('matches the server fixture for all undefined metrics', () => {
    const result = calculateEnvironmental(base, defaultEnvironmentalMetrics())
    expect(result.score).toBe(9.8)
    expect(result.vector).toBe(`${base}/CR:X/IR:X/AR:X/MAV:X/MAC:X/MPR:X/MUI:X/MS:X/MC:X/MI:X/MA:X`)
  })

  it('handles modified scope, privileges and zero impact', () => {
    expect(calculateEnvironmental(
      'CVSS:3.1/AV:N/AC:L/PR:H/UI:N/S:U/C:L/I:L/A:N',
      { ...defaultEnvironmentalMetrics(), MS: 'C', MPR: 'H', CR: 'H', MC: 'H' },
    ).score).toBe(9.1)
    expect(calculateEnvironmental(
      base,
      { ...defaultEnvironmentalMetrics(), MC: 'N', MI: 'N', MA: 'N' },
    ).score).toBe(0)
  })

  it('rejects incomplete and non-v3.1 source vectors', () => {
    expect(() => calculateEnvironmental('CVSS:3.1/AV:N', defaultEnvironmentalMetrics())).toThrow()
    expect(() => calculateEnvironmental(base.replace('3.1', '4.0'), defaultEnvironmentalMetrics())).toThrow()
  })
})
