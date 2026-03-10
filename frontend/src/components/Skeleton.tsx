interface SkeletonProps {
  width?: string | number
  height?: string | number
  borderRadius?: string | number
  className?: string
}

export function Skeleton({
  width = '100%',
  height = 16,
  borderRadius = 'var(--radius-md)',
  className = '',
}: SkeletonProps) {
  return (
    <div
      className={`skeleton ${className}`}
      style={{
        width: typeof width === 'number' ? `${width}px` : width,
        height: typeof height === 'number' ? `${height}px` : height,
        borderRadius: typeof borderRadius === 'number' ? `${borderRadius}px` : borderRadius,
      }}
    />
  )
}

interface SkeletonTextProps {
  lines?: number
  className?: string
}

export function SkeletonText({ lines = 3, className = '' }: SkeletonTextProps) {
  return (
    <div className={`skeleton-text ${className}`}>
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton
          key={i}
          height={14}
          width={i === lines - 1 ? '60%' : '100%'}
        />
      ))}
    </div>
  )
}

interface SkeletonCardProps {
  hasAvatar?: boolean
  hasImage?: boolean
  lines?: number
  className?: string
}

export function SkeletonCard({
  hasAvatar = true,
  hasImage = false,
  lines = 2,
  className = '',
}: SkeletonCardProps) {
  return (
    <div className={`skeleton-card ${className}`}>
      {hasImage && (
        <Skeleton height={120} borderRadius="var(--radius-lg)" className="skeleton-card-image" />
      )}
      <div className="skeleton-card-content">
        {hasAvatar && (
          <div className="skeleton-card-header">
            <Skeleton width={40} height={40} borderRadius="50%" />
            <div className="skeleton-card-meta">
              <Skeleton width="60%" height={14} />
              <Skeleton width="40%" height={12} />
            </div>
          </div>
        )}
        <SkeletonText lines={lines} />
      </div>
    </div>
  )
}

interface SkeletonListProps {
  count?: number
  itemHeight?: number
  gap?: number
  className?: string
}

export function SkeletonList({
  count = 5,
  itemHeight = 48,
  gap = 8,
  className = '',
}: SkeletonListProps) {
  return (
    <div className={`skeleton-list ${className}`} style={{ gap }}>
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="skeleton-list-item" style={{ height: itemHeight }}>
          <Skeleton width={32} height={32} borderRadius="var(--radius-md)" />
          <div className="skeleton-list-item-content">
            <Skeleton width="70%" height={14} />
            <Skeleton width="40%" height={12} />
          </div>
        </div>
      ))}
    </div>
  )
}
