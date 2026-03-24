import type { AssistantChatMessage } from '../services/api'

export interface StoredChatConversation {
  id: string
  projectId: number
  title: string
  updatedAt: string
  messages: AssistantChatMessage[]
}

const STORAGE_KEY = 'genesis_chat_conversations_v1'
export const CHAT_CONVERSATIONS_CHANGED = 'genesis-chat-conversations-changed'

function dedupe(items: StoredChatConversation[]): StoredChatConversation[] {
  const byFingerprint = new Map<string, StoredChatConversation>()
  for (const item of items) {
    const fingerprint = [
      item.projectId,
      item.title.trim(),
      JSON.stringify(item.messages),
    ].join('::')
    const existing = byFingerprint.get(fingerprint)
    if (!existing || existing.updatedAt < item.updatedAt) {
      byFingerprint.set(fingerprint, item)
    }
  }
  return Array.from(byFingerprint.values())
}

function loadAll(): StoredChatConversation[] {
  if (typeof window === 'undefined') return []
  const raw = window.localStorage.getItem(STORAGE_KEY)
  if (!raw) return []
  try {
    const parsed = JSON.parse(raw) as StoredChatConversation[]
    return Array.isArray(parsed) ? dedupe(parsed) : []
  } catch {
    return []
  }
}

function persistAll(items: StoredChatConversation[]) {
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(dedupe(items)))
  window.dispatchEvent(new CustomEvent(CHAT_CONVERSATIONS_CHANGED))
}

export function listChatConversations(projectId: number | null): StoredChatConversation[] {
  if (projectId == null) return []
  return loadAll()
    .filter((item) => item.projectId === projectId)
    .sort((a, b) => (a.updatedAt < b.updatedAt ? 1 : -1))
}

export function getChatConversation(id: string): StoredChatConversation | null {
  return loadAll().find((item) => item.id === id) ?? null
}

export function upsertChatConversation(conversation: StoredChatConversation) {
  const items = loadAll()
  const next = items.filter((item) => item.id !== conversation.id)
  next.push(conversation)
  persistAll(next)
}

export function deleteChatConversation(id: string) {
  const items = loadAll().filter((item) => item.id !== id)
  persistAll(items)
}

export function createConversationId() {
  return `conv_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`
}

export function summarizeConversationTitle(messages: AssistantChatMessage[], fallback: string) {
  const userMessage = messages.find((item) => item.role === 'user' && item.content.trim())
  if (!userMessage) return fallback
  const firstLine = userMessage.content.trim().split('\n')[0].trim()
  return firstLine.length > 42 ? `${firstLine.slice(0, 42)}...` : firstLine
}
