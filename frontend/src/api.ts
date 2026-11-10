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
  /** "album": a photo album (Fotos). */
  kind: 'files' | 'album'
  takenOn: string | null
  membersUpload: boolean
  coverFileId: number | null
  canUpload?: boolean
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
  isPhoto: boolean
  width: number | null
  height: number | null
  /** In an album: the caption (the description) and who is on it. */
  caption?: string | null
  tags?: { memberId: number; name: string }[]
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
  canUpload: boolean
  memberId: number | null
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
  kind?: 'files' | 'album'
  takenOn?: string | null
  membersUpload?: boolean
  coverFileId?: number | null
}

const BASE = '/app/documents'
const json = { 'Content-Type': 'application/json' }

export const QK = {
  all: ['documents'] as const,
  library: ['documents', 'library'] as const,
  folder: (id: number) => ['documents', 'folder', id] as const,
  search: (q: string) => ['documents', 'search', q] as const,
  options: ['documents', 'access-options'] as const,
  albums: ['documents', 'albums'] as const,
  consent: ['documents', 'photo-consent'] as const,
  image: (id: number, size: 'thumb' | 'full') => ['documents', 'image', id, size] as const,
}

// ── Photo albums ──

export const listAlbums = () => apiFetch<{ albums: Folder[]; canManage: boolean }>(`${BASE}/albums`)
export const getConsent = () => apiFetch<{ photosOfMe: boolean }>(`${BASE}/photo-consent`)
export const setConsent = (allowed: boolean) =>
  apiFetch<{ photosOfMe: boolean }>(`${BASE}/photo-consent`, {
    method: 'PUT',
    headers: json,
    body: JSON.stringify({ allowed }),
  })

export async function uploadPhotos(albumId: number, files: File[]) {
  const form = new FormData()
  for (const f of files) form.append('photos', f)
  const res = await apiFetchRaw(`${BASE}/folders/${albumId}/photos`, { method: 'POST', body: form })
  return (await res.json()) as { added: DocFile[]; failed: { name: string; reason: string }[] }
}

export const updatePhoto = (id: number, body: { caption: string | null }) =>
  apiFetch<DocFile>(`${BASE}/photos/${id}`, { method: 'PATCH', headers: json, body: JSON.stringify(body) })
export const deletePhoto = (id: number) => apiFetch<void>(`${BASE}/photos/${id}`, { method: 'DELETE' })
export const setTags = (id: number, memberIds: number[]) =>
  apiFetch<void>(`${BASE}/files/${id}/tags`, { method: 'PUT', headers: json, body: JSON.stringify({ memberIds }) })
export const untagMe = (id: number) => apiFetch<void>(`${BASE}/files/${id}/tags/me`, { method: 'DELETE' })

/** A photo as an object URL (the request needs the session, so no plain src). */
export async function photoUrl(id: number, size: 'thumb' | 'full') {
  const path = size === 'thumb' ? `${BASE}/files/${id}/thumb` : `${BASE}/files/${id}/download?inline=1`
  const res = await apiFetchRaw(path)
  return URL.createObjectURL(await res.blob())
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
