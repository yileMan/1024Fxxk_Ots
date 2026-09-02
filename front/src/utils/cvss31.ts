export const environmentalMetricOrder = [
  'CR', 'IR', 'AR', 'MAV', 'MAC', 'MPR', 'MUI', 'MS', 'MC', 'MI', 'MA',
] as const
export type EnvironmentalMetric = typeof environmentalMetricOrder[number]
export type EnvironmentalMetrics = Record<EnvironmentalMetric, string>

const baseOrder = ['AV', 'AC', 'PR', 'UI', 'S', 'C', 'I', 'A'] as const
const av: Record<string, number> = { N: .85, A: .62, L: .55, P: .2 }
const ac: Record<string, number> = { L: .77, H: .44 }
const ui: Record<string, number> = { N: .85, R: .62 }
const impact: Record<string, number> = { N: 0, L: .22, H: .56 }
const requirement: Record<string, number> = { X: 1, L: .5, M: 1, H: 1.5 }
const pr: Record<string, Record<string, number>> = {
  U: { N: .85, L: .62, H: .27 }, C: { N: .85, L: .68, H: .5 },
}

export function defaultEnvironmentalMetrics(): EnvironmentalMetrics {
  return Object.fromEntries(environmentalMetricOrder.map(key => [key, 'X'])) as EnvironmentalMetrics
}

function parseBaseVector(vector: string): Record<string, string> {
  if (!vector.startsWith('CVSS:3.1/')) throw new Error('仅支持 CVSS v3.1 基础向量')
  const parsed: Record<string, string> = {}
  for (const item of vector.split('/').slice(1)) {
    const parts = item.split(':')
    if (parts.length !== 2 || !baseOrder.includes(parts[0] as typeof baseOrder[number]) || parsed[parts[0]]) {
      throw new Error('来源向量格式无效')
    }
    parsed[parts[0]] = parts[1]
  }
  if (baseOrder.some(key => !parsed[key])) throw new Error('来源向量不完整')
  return parsed
}

function roundup(value: number): number {
  return Math.ceil((value - 1e-10) * 10) / 10
}

export function calculateEnvironmental(baseVector: string, metrics: EnvironmentalMetrics) {
  const base = parseBaseVector(baseVector)
  const modified = (name: string) => metrics[`M${name}` as EnvironmentalMetric] === 'X'
    ? base[name] : metrics[`M${name}` as EnvironmentalMetric]
  const scope = metrics.MS === 'X' ? base.S : metrics.MS
  const miss = Math.min(
    1 - (1 - requirement[metrics.CR] * impact[modified('C')])
      * (1 - requirement[metrics.IR] * impact[modified('I')])
      * (1 - requirement[metrics.AR] * impact[modified('A')]),
    .915,
  )
  const modifiedImpact = scope === 'U'
    ? 6.42 * miss
    : 7.52 * (miss - .029) - 3.25 * Math.pow(miss * .9731 - .02, 13)
  let score = 0
  if (modifiedImpact > 0) {
    const exploitability = 8.22 * av[modified('AV')] * ac[modified('AC')]
      * pr[scope][modified('PR')] * ui[modified('UI')]
    const subtotal = Math.min((scope === 'C' ? 1.08 : 1) * (modifiedImpact + exploitability), 10)
    score = roundup(roundup(subtotal))
  }
  const environment = environmentalMetricOrder.map(key => `${key}:${metrics[key]}`).join('/')
  const canonicalBase = baseOrder.map(key => `${key}:${base[key]}`).join('/')
  return { score, vector: `CVSS:3.1/${canonicalBase}/${environment}` }
}
