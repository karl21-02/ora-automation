import { Building2, FolderGit2, Settings2 } from 'lucide-react'

interface ChatContextBarProps {
  orgName: string | null
  selectedProjects: string[]
  onEditContext?: () => void
}

export default function ChatContextBar({
  orgName,
  selectedProjects,
  onEditContext,
}: ChatContextBarProps) {
  const hasContext = orgName || selectedProjects.length > 0

  if (!hasContext) {
    return null
  }

  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      gap: 12,
      padding: '8px 16px',
      backgroundColor: '#f8fafc',
      borderBottom: '1px solid #e2e8f0',
      fontSize: 12,
    }}>
      {/* Organization */}
      {orgName && (
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          padding: '4px 10px',
          backgroundColor: '#dbeafe',
          borderRadius: 6,
          color: '#1e40af',
          fontWeight: 500,
        }}>
          <Building2 size={12} />
          {orgName}
        </div>
      )}

      {/* Selected Projects */}
      {selectedProjects.length > 0 && (
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          color: '#64748b',
        }}>
          <FolderGit2 size={12} />
          <span style={{ fontWeight: 500 }}>
            {selectedProjects.length === 1
              ? selectedProjects[0]
              : `${selectedProjects.length} projects`}
          </span>
          {selectedProjects.length > 1 && (
            <span style={{
              display: 'flex',
              gap: 4,
              marginLeft: 4,
            }}>
              {selectedProjects.slice(0, 3).map((p) => (
                <span
                  key={p}
                  style={{
                    padding: '2px 6px',
                    backgroundColor: '#f1f5f9',
                    borderRadius: 4,
                    fontSize: 11,
                  }}
                >
                  {p}
                </span>
              ))}
              {selectedProjects.length > 3 && (
                <span style={{
                  padding: '2px 6px',
                  backgroundColor: '#f1f5f9',
                  borderRadius: 4,
                  fontSize: 11,
                }}>
                  +{selectedProjects.length - 3}
                </span>
              )}
            </span>
          )}
        </div>
      )}

      {/* Edit button */}
      {onEditContext && (
        <button
          onClick={onEditContext}
          style={{
            marginLeft: 'auto',
            display: 'flex',
            alignItems: 'center',
            gap: 4,
            padding: '4px 8px',
            border: '1px solid #e2e8f0',
            borderRadius: 4,
            backgroundColor: '#fff',
            color: '#64748b',
            fontSize: 11,
            cursor: 'pointer',
          }}
        >
          <Settings2 size={11} />
          Edit
        </button>
      )}
    </div>
  )
}
