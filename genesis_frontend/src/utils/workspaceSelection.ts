const STORAGE_KEY = 'genesis_confirmed_project_v1'

export function getConfirmedProjectId(): number | null {
  if (typeof window === 'undefined') return null
  const raw = window.localStorage.getItem(STORAGE_KEY)
  if (!raw) return null
  const value = Number(raw)
  return Number.isFinite(value) && value > 0 ? value : null
}

export function setConfirmedProjectId(projectId: number | null) {
  if (typeof window === 'undefined') return
  if (projectId == null) {
    window.localStorage.removeItem(STORAGE_KEY)
    return
  }
  window.localStorage.setItem(STORAGE_KEY, String(projectId))
}
