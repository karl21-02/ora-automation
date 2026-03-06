import { useMemo } from 'react'
import type { OrganizationDetail } from '../types'

interface Props {
  org: OrganizationDetail
  onSelectAgent: (agentId: string) => void
}

const TIER_LABELS: Record<number, string> = {
  4: 'C-Level',
  3: 'Directors',
  2: 'Leads',
  1: 'Specialists',
}

const TIER_COLORS: Record<number, { bg: string; border: string; text: string }> = {
  4: { bg: '#fef2f2', border: '#fca5a5', text: '#991b1b' },
  3: { bg: '#fff7ed', border: '#fdba74', text: '#9a3412' },
  2: { bg: '#eff6ff', border: '#93c5fd', text: '#1e40af' },
  1: { bg: '#f9fafb', border: '#d1d5db', text: '#374151' },
}

export default function OrgChart({ org, onSelectAgent }: Props) {
  const tiers = useMemo(() => {
    const grouped: Record<number, typeof org.agents> = {}
    for (const agent of org.agents) {
      const tier = agent.tier || 1
      if (!grouped[tier]) grouped[tier] = []
      grouped[tier].push(agent)
    }
    return grouped
  }, [org.agents])

  return (
    <div style={{ flex: 1, overflow: 'auto', padding: '16px' }}>
      {[4, 3, 2, 1].map(tier => {
        const agents = tiers[tier]
        if (!agents || agents.length === 0) return null
        const colors = TIER_COLORS[tier] || TIER_COLORS[1]
        return (
          <div key={tier} style={{ marginBottom: 24 }}>
            <div style={{
              fontSize: 12,
              fontWeight: 600,
              color: colors.text,
              marginBottom: 8,
              display: 'flex',
              alignItems: 'center',
              gap: 8,
            }}>
              <span style={{
                padding: '2px 8px',
                borderRadius: 4,
                backgroundColor: colors.bg,
                border: `1px solid ${colors.border}`,
              }}>
                Tier {tier}
              </span>
              {TIER_LABELS[tier]}
            </div>
            <div style={{
              display: 'flex',
              flexWrap: 'wrap',
              gap: 8,
              justifyContent: 'center',
            }}>
              {agents.map(agent => (
                <div
                  key={agent.id}
                  onClick={() => onSelectAgent(agent.id)}
                  style={{
                    padding: '10px 14px',
                    borderRadius: 8,
                    border: `1px solid ${colors.border}`,
                    backgroundColor: colors.bg,
                    cursor: 'pointer',
                    minWidth: 120,
                    textAlign: 'center',
                    opacity: agent.enabled ? 1 : 0.5,
                    transition: 'box-shadow 0.15s',
                  }}
                >
                  <div style={{ fontWeight: 600, fontSize: 13, color: colors.text }}>
                    {agent.display_name}
                  </div>
                  {agent.display_name_ko && (
                    <div style={{ fontSize: 11, color: '#6b7280', marginTop: 2 }}>
                      {agent.display_name_ko.length > 20
                        ? agent.display_name_ko.slice(0, 20) + '...'
                        : agent.display_name_ko}
                    </div>
                  )}
                  <div style={{ fontSize: 10, color: '#9ca3af', marginTop: 4 }}>
                    {agent.team || 'no team'} &middot; {agent.role || 'no role'}
                  </div>
                </div>
              ))}
            </div>
            {tier > 1 && tiers[tier - 1] && (
              <div style={{ textAlign: 'center', padding: '8px 0', color: '#d1d5db' }}>|</div>
            )}
          </div>
        )
      })}
    </div>
  )
}
