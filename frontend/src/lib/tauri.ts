/**
 * Tauri-specific functionality for local file system access
 */

export interface LocalGitRepo {
  name: string
  path: string
  language: string | null
}

/**
 * Check if running in Tauri environment
 */
export function isTauri(): boolean {
  return typeof window !== 'undefined' && window.__TAURI_INTERNALS__ !== undefined
}

/**
 * Open folder picker dialog and return selected path
 */
export async function pickFolder(): Promise<string | null> {
  if (!isTauri()) {
    console.warn('pickFolder is only available in Tauri')
    return null
  }

  const { open } = await import('@tauri-apps/plugin-dialog')
  const result = await open({
    directory: true,
    multiple: false,
    title: 'Select folder to scan for Git repositories',
  })

  return result as string | null
}

/**
 * Scan a folder for Git repositories using Tauri command
 */
export async function scanGitRepos(folderPath: string, maxDepth?: number): Promise<LocalGitRepo[]> {
  if (!isTauri()) {
    console.warn('scanGitRepos is only available in Tauri')
    return []
  }

  const { invoke } = await import('@tauri-apps/api/core')
  return invoke<LocalGitRepo[]>('scan_git_repos', {
    folderPath,
    maxDepth: maxDepth ?? 3,
  })
}

/**
 * Pick a folder and scan it for Git repos
 */
export async function pickAndScanFolder(): Promise<{ path: string; repos: LocalGitRepo[] } | null> {
  const path = await pickFolder()
  if (!path) return null

  const repos = await scanGitRepos(path)
  return { path, repos }
}
