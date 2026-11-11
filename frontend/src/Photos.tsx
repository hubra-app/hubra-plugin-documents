import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  ActionIcon,
  AspectRatio,
  Badge,
  Box,
  Button,
  Center,
  FileButton,
  Group,
  Loader,
  Paper,
  Pill,
  SimpleGrid,
  Stack,
  Switch,
  Text,
  TextInput,
  UnstyledButton,
} from '@mantine/core'
import { IconChevronLeft, IconChevronRight, IconLock, IconPhoto, IconPlus, IconUpload } from '@tabler/icons-react'
import { ConfirmModal, EmptyState, ErrorBanner, Field, LoadingSpinner, MemberPicker, Modal, useT, useToast } from '@hubra/plugin-sdk'
import {
  QK,
  deletePhoto,
  getConsent,
  listAlbums,
  photoUrl,
  setConsent,
  setTags,
  untagMe,
  updateFolder,
  updatePhoto,
  uploadPhotos,
  type DocFile,
  type Folder,
  type FolderView,
} from './api'

function errorText(err: unknown) {
  return err instanceof Error ? err.message : String(err)
}

function useAction() {
  const { notify } = useToast()
  const [busy, setBusy] = useState(false)
  const run = async (fn: () => Promise<unknown>, ok?: string) => {
    setBusy(true)
    try {
      await fn()
      if (ok) notify('success', ok)
      return true
    } catch (err) {
      notify('error', errorText(err))
      return false
    } finally {
      setBusy(false)
    }
  }
  return { busy, run }
}

function fmtDate(iso: string, lang: string | undefined) {
  return new Date(iso).toLocaleDateString(lang?.startsWith('de') ? 'de-CH' : 'en-GB', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  })
}

/** A photo from the club's file store (it needs the session, so no plain src). */
function Picture({
  id,
  size = 'thumb',
  fit = 'cover',
  alt = '',
}: {
  id: number | null
  size?: 'thumb' | 'full'
  fit?: 'cover' | 'contain'
  alt?: string
}) {
  const img = useQuery({
    queryKey: QK.image(id ?? 0, size),
    queryFn: () => photoUrl(id!, size),
    enabled: !!id,
    staleTime: Infinity,
    gcTime: 30 * 60_000,
  })
  const frame = { width: '100%', height: '100%', background: 'var(--mantine-color-default-hover)' }
  if (!id || img.error)
    return (
      <Center style={frame}>
        <IconPhoto size={28} color="var(--mantine-color-dimmed)" />
      </Center>
    )
  if (!img.data)
    return (
      <Center style={frame}>
        <Loader size="sm" />
      </Center>
    )
  return <Box component="img" src={img.data} alt={alt} style={{ ...frame, objectFit: fit, display: 'block' }} />
}

/** Documents › Fotos: the albums open to me, newest first. */
export function PhotosView({ onNewAlbum }: { onNewAlbum: () => void }) {
  const { t, i18n } = useT()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const albums = useQuery({ queryKey: QK.albums, queryFn: listAlbums })
  const consent = useQuery({ queryKey: QK.consent, queryFn: getConsent })
  const { busy, run } = useAction()

  if (albums.error) return <ErrorBanner message={errorText(albums.error)} onRetry={() => albums.refetch()} />
  if (albums.isLoading) return <LoadingSpinner />
  const list = albums.data?.albums ?? []
  const canManage = !!albums.data?.canManage

  return (
    <Stack gap="md">
      <Group justify="space-between" wrap="wrap" gap="sm">
        <Switch
          checked={consent.data?.photosOfMe ?? true}
          disabled={busy || !consent.data}
          onChange={(e) => {
            const allowed = e.currentTarget.checked
            void run(async () => {
              await setConsent(allowed)
              qc.invalidateQueries({ queryKey: QK.all })
            }, allowed ? t('documents.photos.consentOn') : t('documents.photos.consentOff'))
          }}
          label={t('documents.photos.consent')}
          description={t('documents.photos.consentHint')}
        />
        {canManage && (
          <Button leftSection={<IconPlus size={16} />} onClick={onNewAlbum}>
            {t('documents.photos.newAlbum')}
          </Button>
        )}
      </Group>
      {!list.length ? (
        <EmptyState
          icon={<IconPhoto size={28} />}
          title={t('documents.photos.none')}
          description={canManage ? t('documents.photos.noneHint') : undefined}
        />
      ) : (
        <SimpleGrid cols={{ base: 1, xs: 2, md: 3 }} spacing="md">
          {list.map((a) => (
            <Paper
              key={a.id}
              withBorder
              radius="md"
              style={{ overflow: 'hidden', cursor: 'pointer' }}
              onClick={() => navigate(`/app/documents/${a.id}`)}
            >
              <AspectRatio ratio={4 / 3}>
                <Picture id={a.coverFileId} alt={a.name} />
              </AspectRatio>
              <Stack gap={2} p="sm">
                <Group gap={6} wrap="nowrap">
                  <Text fw={600} lineClamp={1}>
                    {a.name}
                  </Text>
                  {a.restricted && <IconLock size={14} color="var(--mantine-color-dimmed)" />}
                </Group>
                <Text size="xs" c="dimmed">
                  {[a.takenOn ? fmtDate(a.takenOn, i18n.language) : null, t('documents.photos.count', { count: a.fileCount })]
                    .filter(Boolean)
                    .join(' · ')}
                </Text>
              </Stack>
            </Paper>
          ))}
        </SimpleGrid>
      )}
    </Stack>
  )
}

/** One album: the photos as a grid, opening one shows it large. */
export function AlbumView({ view }: { view: FolderView }) {
  const { t, i18n } = useT()
  const qc = useQueryClient()
  const { notify } = useToast()
  const [open, setOpen] = useState<number | null>(null)
  const [uploading, setUploading] = useState(false)
  const photos = view.files
  const album = view.folder

  const upload = async (files: File[]) => {
    if (!files.length) return
    setUploading(true)
    try {
      for (let i = 0; i < files.length; i += 20) {
        const done = await uploadPhotos(album.id, files.slice(i, i + 20))
        if (done.added.length) notify('success', t('documents.photos.uploaded', { count: done.added.length }))
        for (const f of done.failed) notify('error', `${f.name}: ${f.reason}`)
      }
    } catch (err) {
      notify('error', errorText(err))
    } finally {
      setUploading(false)
      qc.invalidateQueries({ queryKey: QK.all })
    }
  }
  const index = open === null ? -1 : photos.findIndex((p) => p.id === open)

  return (
    <Stack gap="md">
      <Group justify="space-between" wrap="wrap" gap="sm">
        <Text size="sm" c="dimmed">
          {[album.takenOn ? fmtDate(album.takenOn, i18n.language) : null, t('documents.photos.count', { count: photos.length })]
            .filter(Boolean)
            .join(' · ')}
        </Text>
        {view.canUpload && (
          <FileButton onChange={upload} accept="image/jpeg,image/png,image/webp,image/gif" multiple>
            {(props) => (
              <Button {...props} leftSection={<IconUpload size={16} />} loading={uploading}>
                {t('documents.photos.upload')}
              </Button>
            )}
          </FileButton>
        )}
      </Group>
      {!photos.length ? (
        <EmptyState
          icon={<IconPhoto size={28} />}
          title={t('documents.photos.empty')}
          description={view.canUpload ? t('documents.photos.emptyHint') : undefined}
        />
      ) : (
        <SimpleGrid cols={{ base: 2, sm: 3, md: 4, lg: 5 }} spacing={6}>
          {photos.map((p) => (
            <UnstyledButton
              key={p.id}
              onClick={() => setOpen(p.id)}
              aria-label={p.caption || t('documents.photos.photo')}
              style={{ borderRadius: 6, overflow: 'hidden' }}
            >
              <AspectRatio ratio={1}>
                <Picture id={p.id} alt={p.caption ?? ''} />
              </AspectRatio>
            </UnstyledButton>
          ))}
        </SimpleGrid>
      )}
      {index >= 0 && (
        <PhotoModal
          album={album}
          canManage={view.canManage}
          photo={photos[index]}
          me={view.memberId ?? 0}
          onClose={() => setOpen(null)}
          onStep={(d) => setOpen(photos[(index + d + photos.length) % photos.length].id)}
        />
      )}
    </Stack>
  )
}

function PhotoModal({
  album,
  canManage,
  photo,
  me,
  onClose,
  onStep,
}: {
  album: Folder
  canManage: boolean
  photo: DocFile
  me: number
  onClose: () => void
  onStep: (d: number) => void
}) {
  const { t } = useT()
  const qc = useQueryClient()
  const { busy, run } = useAction()
  const [caption, setCaption] = useState<string | null>(null)
  const [confirm, setConfirm] = useState(false)
  const refresh = () => qc.invalidateQueries({ queryKey: QK.all })
  const tagged = photo.tags ?? []
  const ids = tagged.map((tg) => tg.memberId)
  const tag = (next: number[]) => run(() => setTags(photo.id, next).then(refresh))

  return (
    <Modal
      open
      wide
      onClose={onClose}
      title={photo.caption || album.name}
      footer={
        <Group justify="space-between" w="100%" wrap="wrap" gap="xs">
          <Group gap="xs">
            <ActionIcon variant="default" size="lg" onClick={() => onStep(-1)} aria-label={t('documents.photos.previous')}>
              <IconChevronLeft size={18} />
            </ActionIcon>
            <ActionIcon variant="default" size="lg" onClick={() => onStep(1)} aria-label={t('documents.photos.next')}>
              <IconChevronRight size={18} />
            </ActionIcon>
          </Group>
          <Group gap="xs">
            {canManage && album.coverFileId !== photo.id && (
              <Button
                variant="default"
                onClick={() => run(() => updateFolder(album.id, { coverFileId: photo.id }).then(refresh), t('documents.photos.coverSet'))}
              >
                {t('documents.photos.makeCover')}
              </Button>
            )}
            {photo.canChange && (
              <Button variant="subtle" color="red" onClick={() => setConfirm(true)}>
                {t('documents.delete')}
              </Button>
            )}
          </Group>
        </Group>
      }
    >
      <Stack gap="sm">
        <div style={{ height: 'min(50vh, 480px)', borderRadius: 8, overflow: 'hidden' }}>
          <Picture id={photo.id} size="full" fit="contain" alt={photo.caption ?? ''} />
        </div>
        {photo.uploadedByName && (
          <Text size="xs" c="dimmed">
            {t('documents.photos.by', { name: photo.uploadedByName })}
          </Text>
        )}
        {photo.canChange && (
          <Field label={t('documents.photos.caption')}>
            <TextInput
              value={caption ?? photo.caption ?? ''}
              maxLength={500}
              onChange={(e) => setCaption(e.currentTarget.value)}
              onBlur={() => {
                if (caption !== null && caption !== (photo.caption ?? ''))
                  void run(() => updatePhoto(photo.id, { caption: caption || null }).then(refresh))
                setCaption(null)
              }}
            />
          </Field>
        )}
        <div>
          <Text size="sm" fw={600} mb={6}>
            {t('documents.photos.onPhoto')}
          </Text>
          <Group gap={6} wrap="wrap">
            {tagged.length === 0 && (
              <Text size="sm" c="dimmed">
                {t('documents.photos.nobodyTagged')}
              </Text>
            )}
            {tagged.map((tg) =>
              photo.canChange ? (
                <Pill key={tg.memberId} withRemoveButton onRemove={() => tag(ids.filter((m) => m !== tg.memberId))} size="md">
                  {tg.name}
                </Pill>
              ) : (
                <Badge key={tg.memberId} variant="light" color="gray" style={{ textTransform: 'none' }}>
                  {tg.name}
                </Badge>
              ),
            )}
          </Group>
          {photo.canChange && (
            <MemberPicker
              mt="xs"
              value={null}
              placeholder={t('documents.photos.tagSomeone')}
              exclude={ids.map(String)}
              disabled={busy}
              onChange={(mid) => mid && tag([...ids, Number(mid)])}
            />
          )}
          {ids.includes(me) && !photo.canChange && (
            <Button
              mt="xs"
              size="xs"
              variant="subtle"
              onClick={() => run(() => untagMe(photo.id).then(refresh), t('documents.photos.untagged'))}
            >
              {t('documents.photos.untagMe')}
            </Button>
          )}
        </div>
      </Stack>
      <ConfirmModal
        open={confirm}
        title={t('documents.photos.deletePhotoTitle')}
        body={t('documents.photos.deletePhotoBody')}
        confirmLabel={t('documents.delete')}
        onClose={() => setConfirm(false)}
        onConfirm={async () => {
          setConfirm(false)
          if (await run(() => deletePhoto(photo.id))) {
            refresh()
            onClose()
          }
        }}
      />
    </Modal>
  )
}
