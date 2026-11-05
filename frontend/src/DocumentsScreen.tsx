import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  ActionIcon,
  Anchor,
  Badge,
  Breadcrumbs,
  Button,
  FileInput,
  Group,
  Menu,
  MultiSelect,
  Paper,
  SegmentedControl,
  Select,
  SimpleGrid,
  Stack,
  Table,
  Text,
  TextInput,
  Textarea,
  UnstyledButton,
} from '@mantine/core'
import {
  IconDots,
  IconDownload,
  IconEye,
  IconFile,
  IconFileTypePdf,
  IconFolder,
  IconFolderPlus,
  IconLock,
  IconPhoto,
  IconSearch,
  IconUpload,
} from '@tabler/icons-react'
import {
  ConfirmModal,
  EmptyState,
  ErrorBanner,
  Field,
  LoadingSpinner,
  Modal,
  PageHead,
  formatDateTime,
  useT,
  useToast,
} from '@hubra/plugin-sdk'
import {
  INLINE_TYPES,
  QK,
  createFolder,
  deleteFile,
  deleteFolder,
  formatSize,
  getAccessOptions,
  getFolder,
  getLibrary,
  openFile,
  replaceFile,
  searchFiles,
  updateFile,
  updateFolder,
  uploadFile,
  type DocFile,
  type Folder,
  type Library,
} from './api'

function fileIcon(type: string) {
  if (type === 'application/pdf') return <IconFileTypePdf size={18} />
  if (type.startsWith('image/')) return <IconPhoto size={18} />
  return <IconFile size={18} />
}

function errorText(err: unknown) {
  return err instanceof Error ? err.message : String(err)
}

export function DocumentsScreen() {
  const { t } = useT()
  const { notify } = useToast()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const params = useParams()
  const folderId = params.folderId ? Number(params.folderId) : null
  const [q, setQ] = useState('')
  const [search, setSearch] = useState('')
  useEffect(() => {
    const id = setTimeout(() => setSearch(q.trim()), 250)
    return () => clearTimeout(id)
  }, [q])

  const library = useQuery({ queryKey: QK.library, queryFn: getLibrary })
  const folder = useQuery({
    queryKey: QK.folder(folderId ?? 0),
    queryFn: () => getFolder(folderId as number),
    enabled: folderId !== null,
  })
  const results = useQuery({
    queryKey: QK.search(search),
    queryFn: () => searchFiles(search),
    enabled: search.length > 0,
  })

  const [upload, setUpload] = useState(false)
  const [folderForm, setFolderForm] = useState<Folder | 'new' | null>(null)
  const [fileForm, setFileForm] = useState<DocFile | null>(null)
  const [newVersion, setNewVersion] = useState<DocFile | null>(null)
  const [deleting, setDeleting] = useState<{ kind: 'file'; item: DocFile } | { kind: 'folder'; item: Folder } | null>(null)

  const refresh = () => qc.invalidateQueries({ queryKey: QK.all })
  const view: Library | undefined = folderId === null ? library.data : folder.data
  const loading = folderId === null ? library.isLoading : folder.isLoading
  const error = folderId === null ? library.error : folder.error
  const allFolders = library.data?.folders ?? []
  const subfolders = folderId === null ? allFolders.filter((f) => f.parentId === null) : (view?.folders ?? [])
  const canWrite = !!view?.canWrite
  const canManage = !!view?.canManage

  const open = (doc: DocFile, inline: boolean) =>
    openFile(doc, inline).catch((err) => notify('error', errorText(err)))

  const confirmDelete = async () => {
    if (!deleting) return
    try {
      if (deleting.kind === 'file') await deleteFile(deleting.item.id)
      else await deleteFolder(deleting.item.id)
      notify('success', t('documents.deleted'))
      if (deleting.kind === 'folder' && deleting.item.id === folderId) {
        navigate(deleting.item.parentId ? `/app/documents/${deleting.item.parentId}` : '/app/documents')
      }
      refresh()
    } catch (err) {
      notify('error', errorText(err))
    }
    setDeleting(null)
  }

  const title = folderId !== null && folder.data ? folder.data.folder.name : t('documents.title')

  return (
    <>
      <PageHead
        title={title}
        desc={folderId !== null ? (folder.data?.folder.description ?? undefined) : t('documents.desc')}
        actions={
          <Group gap="xs">
            {canManage && (
              <Button variant="default" leftSection={<IconFolderPlus size={16} />} onClick={() => setFolderForm('new')}>
                {t('documents.newFolder')}
              </Button>
            )}
            {canWrite && (
              <Button leftSection={<IconUpload size={16} />} onClick={() => setUpload(true)}>
                {t('documents.upload')}
              </Button>
            )}
          </Group>
        }
      />
      <Stack gap="md">
        <Group justify="space-between" wrap="wrap" gap="sm">
          <Breadcrumbs separatorMargin={6} style={{ flexWrap: 'wrap' }}>
            <Anchor component="button" onClick={() => navigate('/app/documents')}>
              {t('documents.title')}
            </Anchor>
            {folder.data?.path.map((p) => (
              <Anchor key={p.id} component="button" onClick={() => navigate(`/app/documents/${p.id}`)}>
                {p.name}
              </Anchor>
            ))}
            {folderId !== null && folder.data && <Text size="sm">{folder.data.folder.name}</Text>}
          </Breadcrumbs>
          <TextInput
            leftSection={<IconSearch size={16} />}
            placeholder={t('documents.search')}
            value={q}
            onChange={(e) => setQ(e.currentTarget.value)}
            w={{ base: '100%', xs: 260 }}
            aria-label={t('documents.search')}
          />
        </Group>

        {error ? (
          <ErrorBanner message={errorText(error)} onRetry={refresh} />
        ) : loading ? (
          <LoadingSpinner />
        ) : search ? (
          <FileTable
            files={results.data ?? []}
            showFolder
            onOpen={open}
            onEdit={setFileForm}
            onVersion={setNewVersion}
            onDelete={(item) => setDeleting({ kind: 'file', item })}
            empty={results.isLoading ? t('documents.loading') : t('documents.noHits')}
          />
        ) : (
          <>
            {subfolders.length > 0 && (
              <SimpleGrid cols={{ base: 1, xs: 2, md: 3, lg: 4 }} spacing="sm">
                {subfolders.map((f) => (
                  <FolderCard
                    key={f.id}
                    folder={f}
                    canManage={canManage}
                    onOpen={() => navigate(`/app/documents/${f.id}`)}
                    onEdit={() => setFolderForm(f)}
                    onDelete={() => setDeleting({ kind: 'folder', item: f })}
                  />
                ))}
              </SimpleGrid>
            )}
            {(view?.files.length ?? 0) > 0 || subfolders.length === 0 ? (
              <FileTable
                files={view?.files ?? []}
                onOpen={open}
                onEdit={setFileForm}
                onVersion={setNewVersion}
                onDelete={(item) => setDeleting({ kind: 'file', item })}
                empty={
                  <EmptyState
                    icon={<IconFolder size={28} />}
                    title={t('documents.empty')}
                    description={canWrite ? t('documents.emptyHint') : undefined}
                    action={canWrite ? { label: t('documents.upload'), onClick: () => setUpload(true) } : undefined}
                  />
                }
              />
            ) : null}
          </>
        )}
      </Stack>

      <UploadModal
        open={upload}
        onClose={() => setUpload(false)}
        folderId={folderId}
        onDone={refresh}
      />
      {folderForm && (
        <FolderModal
          folder={folderForm === 'new' ? null : folderForm}
          parentId={folderForm === 'new' ? folderId : folderForm.parentId}
          folders={allFolders}
          onClose={() => setFolderForm(null)}
          onDone={refresh}
        />
      )}
      {fileForm && (
        <FileModal file={fileForm} folders={allFolders} onClose={() => setFileForm(null)} onDone={refresh} />
      )}
      {newVersion && (
        <VersionModal file={newVersion} onClose={() => setNewVersion(null)} onDone={refresh} />
      )}
      <ConfirmModal
        open={!!deleting}
        onClose={() => setDeleting(null)}
        onConfirm={confirmDelete}
        title={t(deleting?.kind === 'folder' ? 'documents.deleteFolderTitle' : 'documents.deleteFileTitle', {
          name: deleting?.item.name ?? '',
        })}
        body={deleting?.kind === 'folder' ? t('documents.deleteFolderBody') : t('documents.deleteFileBody')}
      />
    </>
  )
}

function FolderCard({
  folder,
  canManage,
  onOpen,
  onEdit,
  onDelete,
}: {
  folder: Folder
  canManage: boolean
  onOpen: () => void
  onEdit: () => void
  onDelete: () => void
}) {
  const { t } = useT()
  return (
    <Paper withBorder p="sm" radius="md">
      <Group justify="space-between" wrap="nowrap" gap="xs">
        <UnstyledButton onClick={onOpen} style={{ flex: 1, minWidth: 0 }}>
          <Group gap="sm" wrap="nowrap">
            <IconFolder size={24} style={{ color: 'var(--hb-primary)', flexShrink: 0 }} />
            <Stack gap={0} style={{ minWidth: 0 }}>
              <Text fw={600} lineClamp={2} style={{ overflowWrap: 'anywhere' }}>
                {folder.name}
              </Text>
              <Group gap={6}>
                <Text size="xs" c="dimmed">
                  {t('documents.fileCount', { count: folder.fileCount })}
                </Text>
                {folder.restricted && (
                  <Badge size="xs" variant="light" leftSection={<IconLock size={10} />}>
                    {t('documents.restricted')}
                  </Badge>
                )}
              </Group>
            </Stack>
          </Group>
        </UnstyledButton>
        {canManage && (
          <Menu position="bottom-end" withinPortal>
            <Menu.Target>
              <ActionIcon variant="subtle" aria-label={t('documents.folderActions')}>
                <IconDots size={16} />
              </ActionIcon>
            </Menu.Target>
            <Menu.Dropdown>
              <Menu.Item onClick={onEdit}>{t('documents.editFolder')}</Menu.Item>
              <Menu.Item color="red" onClick={onDelete}>
                {t('documents.delete')}
              </Menu.Item>
            </Menu.Dropdown>
          </Menu>
        )}
      </Group>
    </Paper>
  )
}

function FileTable({
  files,
  showFolder,
  onOpen,
  onEdit,
  onVersion,
  onDelete,
  empty,
}: {
  files: DocFile[]
  showFolder?: boolean
  onOpen: (doc: DocFile, inline: boolean) => void
  onEdit: (doc: DocFile) => void
  onVersion: (doc: DocFile) => void
  onDelete: (doc: DocFile) => void
  empty: React.ReactNode
}) {
  const { t } = useT()
  if (files.length === 0) {
    return typeof empty === 'string' ? (
      <Text c="dimmed" size="sm">
        {empty}
      </Text>
    ) : (
      <>{empty}</>
    )
  }
  return (
    <Paper withBorder radius="md" style={{ overflowX: 'auto' }}>
      <Table verticalSpacing="sm" highlightOnHover>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>{t('documents.name')}</Table.Th>
            <Table.Th visibleFrom="sm">{t('documents.size')}</Table.Th>
            <Table.Th visibleFrom="md">{t('documents.uploadedBy')}</Table.Th>
            <Table.Th visibleFrom="sm">{t('documents.changed')}</Table.Th>
            <Table.Th w={1} />
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {files.map((d) => {
            const inline = INLINE_TYPES.has(d.contentType)
            return (
              <Table.Tr key={d.id}>
                <Table.Td>
                  <UnstyledButton onClick={() => onOpen(d, inline)} style={{ minWidth: 0 }}>
                    <Group gap="sm" wrap="nowrap">
                      <span style={{ color: 'var(--hb-text-muted)', display: 'flex' }}>{fileIcon(d.contentType)}</span>
                      <Stack gap={0} style={{ minWidth: 0 }}>
                        <Text size="sm" fw={500} style={{ overflowWrap: 'anywhere' }}>
                          {d.name}
                        </Text>
                        {(d.description || (showFolder && d.folderName)) && (
                          <Text size="xs" c="dimmed" lineClamp={1}>
                            {[showFolder ? d.folderName : null, d.description].filter(Boolean).join(' · ')}
                          </Text>
                        )}
                      </Stack>
                    </Group>
                  </UnstyledButton>
                </Table.Td>
                <Table.Td visibleFrom="sm">
                  <Text size="sm" c="dimmed" style={{ whiteSpace: 'nowrap' }}>
                    {formatSize(d.size)}
                  </Text>
                </Table.Td>
                <Table.Td visibleFrom="md">
                  <Text size="sm" c="dimmed">
                    {d.uploadedByName ?? '–'}
                  </Text>
                </Table.Td>
                <Table.Td visibleFrom="sm">
                  <Text size="sm" c="dimmed" style={{ whiteSpace: 'nowrap' }}>
                    {d.updatedAt ? formatDateTime(d.updatedAt) : ''}
                  </Text>
                </Table.Td>
                <Table.Td>
                  <Group gap={4} wrap="nowrap" justify="flex-end">
                    {inline && (
                      <ActionIcon variant="subtle" aria-label={t('documents.view')} onClick={() => onOpen(d, true)}>
                        <IconEye size={16} />
                      </ActionIcon>
                    )}
                    <ActionIcon variant="subtle" aria-label={t('documents.download')} onClick={() => onOpen(d, false)}>
                      <IconDownload size={16} />
                    </ActionIcon>
                    {d.canChange && (
                      <Menu position="bottom-end" withinPortal>
                        <Menu.Target>
                          <ActionIcon variant="subtle" aria-label={t('documents.fileActions')}>
                            <IconDots size={16} />
                          </ActionIcon>
                        </Menu.Target>
                        <Menu.Dropdown>
                          <Menu.Item onClick={() => onEdit(d)}>{t('documents.editFile')}</Menu.Item>
                          <Menu.Item onClick={() => onVersion(d)}>{t('documents.newVersion')}</Menu.Item>
                          <Menu.Item color="red" onClick={() => onDelete(d)}>
                            {t('documents.delete')}
                          </Menu.Item>
                        </Menu.Dropdown>
                      </Menu>
                    )}
                  </Group>
                </Table.Td>
              </Table.Tr>
            )
          })}
        </Table.Tbody>
      </Table>
    </Paper>
  )
}

function UploadModal({
  open,
  onClose,
  folderId,
  onDone,
}: {
  open: boolean
  onClose: () => void
  folderId: number | null
  onDone: () => void
}) {
  const { t } = useT()
  const { notify } = useToast()
  const [picked, setPicked] = useState<File[]>([])
  const [description, setDescription] = useState('')
  const [busy, setBusy] = useState(false)

  const close = () => {
    setPicked([])
    setDescription('')
    onClose()
  }
  const submit = async () => {
    setBusy(true)
    let done = 0
    for (const file of picked) {
      try {
        await uploadFile(file, folderId, description.trim())
        done += 1
      } catch (err) {
        notify('error', `${file.name}: ${errorText(err)}`)
      }
    }
    setBusy(false)
    if (done) notify('success', t('documents.uploaded', { count: done }))
    onDone()
    close()
  }
  return (
    <Modal
      open={open}
      onClose={close}
      title={t('documents.upload')}
      onSubmit={(e) => {
        e?.preventDefault()
        void submit()
      }}
      footer={
        <>
          <Button variant="default" onClick={close}>
            {t('documents.cancel')}
          </Button>
          <Button type="submit" loading={busy} disabled={picked.length === 0}>
            {t('documents.upload')}
          </Button>
        </>
      }
    >
      <FileInput
        multiple
        clearable
        label={t('documents.files')}
        placeholder={t('documents.pickFiles')}
        value={picked}
        onChange={setPicked}
        leftSection={<IconUpload size={16} />}
      />
      <Textarea
        label={t('documents.description')}
        autosize
        minRows={2}
        value={description}
        onChange={(e) => setDescription(e.currentTarget.value)}
      />
      <Text size="xs" c="dimmed">
        {t('documents.uploadHint')}
      </Text>
    </Modal>
  )
}

function folderOptions(folders: Folder[], exclude?: number) {
  // A folder can't move into itself or below itself.
  const below = new Set<number>()
  if (exclude !== undefined) {
    below.add(exclude)
    let grew = true
    while (grew) {
      grew = false
      for (const f of folders) {
        if (f.parentId !== null && below.has(f.parentId) && !below.has(f.id)) {
          below.add(f.id)
          grew = true
        }
      }
    }
  }
  const byId = new Map(folders.map((f) => [f.id, f]))
  const label = (f: Folder): string => {
    const parts = [f.name]
    let p = f.parentId
    while (p !== null && byId.has(p)) {
      const parent = byId.get(p) as Folder
      parts.unshift(parent.name)
      p = parent.parentId
    }
    return parts.join(' / ')
  }
  return folders
    .filter((f) => !below.has(f.id))
    .map((f) => ({ value: String(f.id), label: label(f) }))
    .sort((a, b) => a.label.localeCompare(b.label))
}

function FolderModal({
  folder,
  parentId,
  folders,
  onClose,
  onDone,
}: {
  folder: Folder | null
  parentId: number | null
  folders: Folder[]
  onClose: () => void
  onDone: () => void
}) {
  const { t } = useT()
  const { notify } = useToast()
  const options = useQuery({ queryKey: QK.options, queryFn: getAccessOptions })
  const [name, setName] = useState(folder?.name ?? '')
  const [description, setDescription] = useState(folder?.description ?? '')
  const [parent, setParent] = useState<string | null>(parentId !== null ? String(parentId) : null)
  const [mode, setMode] = useState(folder?.restricted ? 'some' : 'all')
  const [roles, setRoles] = useState<string[]>((folder?.roleIds ?? []).map(String))
  const [groups, setGroups] = useState<string[]>((folder?.groupIds ?? []).map(String))
  const [busy, setBusy] = useState(false)
  const parents = useMemo(() => folderOptions(folders, folder?.id), [folders, folder?.id])

  const submit = async () => {
    setBusy(true)
    const body = {
      name: name.trim(),
      description: description.trim() || null,
      parentId: parent ? Number(parent) : null,
      roleIds: mode === 'some' ? roles.map(Number) : [],
      groupIds: mode === 'some' ? groups.map(Number) : [],
    }
    try {
      if (folder) await updateFolder(folder.id, body)
      else await createFolder(body)
      notify('success', t('documents.saved'))
      onDone()
      onClose()
    } catch (err) {
      notify('error', errorText(err))
    }
    setBusy(false)
  }
  const noneChosen = mode === 'some' && roles.length === 0 && groups.length === 0
  return (
    <Modal
      open
      wide
      onClose={onClose}
      title={folder ? t('documents.editFolder') : t('documents.newFolder')}
      onSubmit={(e) => {
        e?.preventDefault()
        void submit()
      }}
      footer={
        <>
          <Button variant="default" onClick={onClose}>
            {t('documents.cancel')}
          </Button>
          <Button type="submit" loading={busy} disabled={!name.trim() || noneChosen}>
            {t('documents.save')}
          </Button>
        </>
      }
    >
      <TextInput label={t('documents.name')} required value={name} onChange={(e) => setName(e.currentTarget.value)} data-autofocus />
      <Textarea
        label={t('documents.description')}
        autosize
        minRows={2}
        value={description}
        onChange={(e) => setDescription(e.currentTarget.value)}
      />
      <Select
        label={t('documents.parent')}
        placeholder={t('documents.topLevel')}
        clearable
        searchable
        data={parents}
        value={parent}
        onChange={setParent}
      />
      <Field label={t('documents.access')} hint={t('documents.accessHint')}>
        <SegmentedControl
          fullWidth
          value={mode}
          onChange={setMode}
          data={[
            { value: 'all', label: t('documents.accessAll') },
            { value: 'some', label: t('documents.accessSome') },
          ]}
        />
      </Field>
      {mode === 'some' && (
        <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="sm">
          <MultiSelect
            label={t('documents.roles')}
            searchable
            data={(options.data?.roles ?? []).map((r) => ({ value: String(r.id), label: r.name }))}
            value={roles}
            onChange={setRoles}
          />
          <MultiSelect
            label={t('documents.groups')}
            searchable
            data={(options.data?.groups ?? []).map((g) => ({ value: String(g.id), label: g.name }))}
            value={groups}
            onChange={setGroups}
          />
        </SimpleGrid>
      )}
    </Modal>
  )
}

function FileModal({
  file,
  folders,
  onClose,
  onDone,
}: {
  file: DocFile
  folders: Folder[]
  onClose: () => void
  onDone: () => void
}) {
  const { t } = useT()
  const { notify } = useToast()
  const [name, setName] = useState(file.name)
  const [description, setDescription] = useState(file.description ?? '')
  const [folder, setFolder] = useState<string | null>(file.folderId !== null ? String(file.folderId) : null)
  const [busy, setBusy] = useState(false)
  const submit = async () => {
    setBusy(true)
    try {
      await updateFile(file.id, {
        name: name.trim(),
        description: description.trim() || null,
        folderId: folder ? Number(folder) : null,
      })
      notify('success', t('documents.saved'))
      onDone()
      onClose()
    } catch (err) {
      notify('error', errorText(err))
    }
    setBusy(false)
  }
  return (
    <Modal
      open
      onClose={onClose}
      title={t('documents.editFile')}
      onSubmit={(e) => {
        e?.preventDefault()
        void submit()
      }}
      footer={
        <>
          <Button variant="default" onClick={onClose}>
            {t('documents.cancel')}
          </Button>
          <Button type="submit" loading={busy} disabled={!name.trim()}>
            {t('documents.save')}
          </Button>
        </>
      }
    >
      <TextInput label={t('documents.name')} required value={name} onChange={(e) => setName(e.currentTarget.value)} />
      <Textarea
        label={t('documents.description')}
        autosize
        minRows={2}
        value={description}
        onChange={(e) => setDescription(e.currentTarget.value)}
      />
      <Select
        label={t('documents.folder')}
        placeholder={t('documents.topLevel')}
        clearable
        searchable
        data={folderOptions(folders)}
        value={folder}
        onChange={setFolder}
      />
    </Modal>
  )
}

function VersionModal({ file, onClose, onDone }: { file: DocFile; onClose: () => void; onDone: () => void }) {
  const { t } = useT()
  const { notify } = useToast()
  const [picked, setPicked] = useState<File | null>(null)
  const [busy, setBusy] = useState(false)
  const submit = async () => {
    if (!picked) return
    setBusy(true)
    try {
      await replaceFile(file.id, picked)
      notify('success', t('documents.saved'))
      onDone()
      onClose()
    } catch (err) {
      notify('error', errorText(err))
    }
    setBusy(false)
  }
  return (
    <Modal
      open
      onClose={onClose}
      title={t('documents.newVersion')}
      subtitle={file.name}
      onSubmit={(e) => {
        e?.preventDefault()
        void submit()
      }}
      footer={
        <>
          <Button variant="default" onClick={onClose}>
            {t('documents.cancel')}
          </Button>
          <Button type="submit" loading={busy} disabled={!picked}>
            {t('documents.upload')}
          </Button>
        </>
      }
    >
      <FileInput
        label={t('documents.files')}
        placeholder={t('documents.pickFile')}
        value={picked}
        onChange={setPicked}
        leftSection={<IconUpload size={16} />}
      />
      <Text size="xs" c="dimmed">
        {t('documents.newVersionHint')}
      </Text>
    </Modal>
  )
}
