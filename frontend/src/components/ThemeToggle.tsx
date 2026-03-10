import { Moon, Sun } from 'lucide-react'
import { useTheme } from '../lib/hooks/useTheme'

interface Props {
  size?: number
}

export default function ThemeToggle({ size = 18 }: Props) {
  const { isDark, toggleTheme } = useTheme()

  return (
    <button
      className="theme-toggle"
      onClick={toggleTheme}
      aria-label={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
      title={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
    >
      {isDark ? <Sun size={size} /> : <Moon size={size} />}
    </button>
  )
}
