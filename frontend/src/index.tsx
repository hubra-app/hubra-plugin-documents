import { registerPlugin } from '@hubra/plugin-sdk'
import { IconFolders } from '@tabler/icons-react'
import { DocumentsScreen } from './DocumentsScreen'
import { searchFiles } from './api'
import translations from './translations.json'

registerPlugin({
  id: 'documents',
  routes: [
    { path: 'documents', module: 'documents', perm: 'documents.files.read', component: DocumentsScreen },
    {
      path: 'documents/:folderId',
      module: 'documents',
      perm: 'documents.files.read',
      component: DocumentsScreen,
    },
  ],
  search: [
    {
      id: 'files',
      module: 'documents',
      perm: 'documents.files.read',
      label: 'shell.searchKind.documents',
      load: async () =>
        (await searchFiles('')).map((d) => ({
          id: d.id,
          label: d.name,
          sub: d.folderName ?? undefined,
          keywords: d.description ?? undefined,
          path: d.folderId ? `/app/documents/${d.folderId}` : '/app/documents',
        })),
    },
  ],
  // The nav entry in hubra_documents/__init__.py names this icon.
  icons: { folders: IconFolders },
  translations,
})
