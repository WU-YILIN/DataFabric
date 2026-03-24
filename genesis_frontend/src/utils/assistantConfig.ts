export interface AssistantRuntimeConfig {
  apiKey: string
  baseUrl: string
  model: string
}

const STORAGE_KEY = 'genesis_assistant_runtime_config_v1'

const DEFAULT_CONFIG: AssistantRuntimeConfig = {
  apiKey: '',
  baseUrl: '',
  model: '',
}

export function getAssistantRuntimeConfig(): AssistantRuntimeConfig {
  if (typeof window === 'undefined') return DEFAULT_CONFIG
  const raw = window.localStorage.getItem(STORAGE_KEY)
  if (!raw) return DEFAULT_CONFIG
  try {
    const parsed = JSON.parse(raw) as Partial<AssistantRuntimeConfig>
    return {
      apiKey: typeof parsed.apiKey === 'string' ? parsed.apiKey : '',
      baseUrl: typeof parsed.baseUrl === 'string' ? parsed.baseUrl : '',
      model: typeof parsed.model === 'string' ? parsed.model : '',
    }
  } catch {
    return DEFAULT_CONFIG
  }
}

export function saveAssistantRuntimeConfig(config: AssistantRuntimeConfig) {
  if (typeof window === 'undefined') return
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(config))
}
