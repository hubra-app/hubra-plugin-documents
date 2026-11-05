import { apiFetch, apiFetchRaw } from '@hubra/plugin-sdk'

export interface Folder {
  id: number
  name: string
  description: string | null
  parentId: number | null
  roleIds: number[]
  groupIds: number[]
  restricted: boolean
  fileCount: number
}

export interface DocFile {
  id: number
  folderId: number | null
  folderName?: string | null
  name: string
  description: string | null
  size: number
  contentType: string
  uploadedBy: number | null
  uploadedByName: string | null
  createdAt: string | null
  updatedAt: string | null
  canChange: boolean
}

export interface Library {
  folders: Folder[]
  files: DocFile[]
  canWrite: boolean
  canManage: boolean
}

export interface FolderView extends Library {
  folder: Folder
  path: { id: number; name: string }[]
}

export interface AccessOptions {
  roles: { id: number; name: string }[]
  groups: { id: number; name: string }[]
}

export interface FolderInput {
  name?: string
  description?: string | null
  parentId?: number | null
  roleIds?: number[]
  groupIds?: number[]
}

const BASE = '/app/documents'
const json = { 'Content-Type': 'application/json' }

export const QK = {
  all: ['documents'] as const,
  library: ['documents', 'library'] as const,
  folder: (id: number) => ['documents', 'folder', id] as const,
  search: (q: string) => ['documents', 'search', q] as const,
  options: ['documents', 'access-options'] as const,
}

export const getLibrary = () => apiFetch<Library>(`${BASE}/library`)
export const getFolder = (id: number) => apiFetch<FolderView>(`${BASE}/folders/${id}`)
export const searchFiles = (q: string) =>
  apiFetch<DocFile[]>(`${BASE}/files?q=${encodeURIComponent(q)}`)
export const getAccessOptions = () => apiFetch<AccessOptions>(`${BASE}/access-options`)

export const createFolder = (body: FolderInput) =>
  apiFetch<Folder>(`${BASE}/folders`, { method: 'POST', headers: json, body: JSON.stringify(body) })
export const updateFolder = (id: number, body: FolderInput) =>
  apiFetch<Folder>(`${BASE}/folders/${id}`, {
    method: 'PATCH',
    headers: json,
    body: JSON.stringify(body),
  })
export const deleteFolder = (id: number) =>
  apiFetch<void>(`${BASE}/folders/${id}`, { method: 'DELETE' })

export async function uploadFile(file: File, folderId: number | null, description: string) {
  const form = new FormData()
  form.append('file', file)
  if (folderId !== null) form.append('folderId', String(folderId))
  if (description) form.append('description', description)
  const res = await apiFetchRaw(`${BASE}/files`, { method: 'POST', body: form })
  return (await res.json()) as DocFile
}

export async function replaceFile(id: number, file: File) {
  const form = new FormData()
  form.append('file', file)
  const res = await apiFetchRaw(`${BASE}/files/${id}/content`, { method: 'PUT', body: form })
  return (await res.json()) as DocFile
}

export const updateFile = (
  id: number,
  body: { name?: string; description?: string | null; folderId?: number | null },
) =>
  apiFetch<DocFile>(`${BASE}/files/${id}`, {
    method: 'PATCH',
    headers: json,
    body: JSON.stringify(body),
  })
export const deleteFile = (id: number) =>
  apiFetch<void>(`${BASE}/files/${id}`, { method: 'DELETE' })

/** Fetches the file with the session and saves or opens it. */
export async function openFile(doc: DocFile, inline: boolean) {
  const res = await apiFetchRaw(`${BASE}/files/${doc.id}/download${inline ? '?inline=1' : ''}`)
  const url = URL.createObjectURL(await res.blob())
  if (inline) {
    window.open(url, '_blank', 'noopener')
  } else {
    const a = document.createElement('a')
    a.href = url
    a.download = doc.name
    document.body.appendChild(a)
    a.click()
    a.remove()
  }
  setTimeout(() => URL.revokeObjectURL(url), 60_000)
}

export const INLINE_TYPES = new Set([
  'application/pdf',
  'image/png',
  'image/jpeg',
  'image/gif',
  'image/webp',
  'text/plain',
])

export function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}
