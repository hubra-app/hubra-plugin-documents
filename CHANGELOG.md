# Documents

## Unreleased

- Security: photos with more than 60 million pixels are refused before they are decoded; a new version of a photo is re-encoded with a new thumbnail; thumbnails are served as the image they are; photo names are cleaned like file names; `%` and `_` in the search match themselves.
- Photos: deleting a photo is red text at the left of the dialog, like other dialogs.
- **Photo albums (Fotos).** Albums move here from the Community plugin. An album is a folder of the kind *album*, with the same access per role and group as any folder. The new *Fotos* view next to the documents (`/app/documents?view=photos`) shows the albums and their photos in a grid. Photos are re-encoded without EXIF and get thumbnails; each has a caption and a cover choice. Members can be tagged on a photo, untag themselves, or turn off *Fotos von mir*. An album may let every member who can see it add photos.
- The albums from Community are taken over by the job `documents-take-over-albums` through Community's contracts (`community.albums.export`, `community.photos.optouts`). Photos are copied in the file store, with captions, tags, covers and opt-outs. Each album is taken once.
- New clubs: the Mitglied role gets *Ansehen*, so members see the folders open to everyone and the albums. Existing clubs give members access under Einstellungen › Rollen if they should see the photos.
- Run `flask db upgrade` after updating.

## 1.1.0

- Gives the standard roles access when a club first switches it on (`role_defaults`, docs/roles.md in hubra-app/hubra): Vorstand Bearbeiten, Aktuar/in Alles. Roles without access don't see it; their own data from it stays on their profile. Needs Hubra 0.2.5 or later.
- Dashboard widget **Neueste Dokumente**: the files changed last, only from folders the member may open (needs `documents.files.read`).

## 1.0.0

First version: the club's document library.

- Folders inside folders. A folder is open to everyone who may read
  documents, or only to the roles and groups it names; a subfolder is only
  open to whoever may open the folder above it too.
- Upload several files at once, rename, move, upload a new version, delete.
  PDFs, images and text files open in the browser; everything else
  downloads.
- Search over names and descriptions of the files you may open, also in the
  app's search (Ctrl K).
- Files are kept in Hubra's file store: encrypted with the club's key, in
  the platform's S3 bucket or on the server, counted towards the club's
  storage and deleted with the club.
- Permissions: `documents.files.read`, `documents.files.write` (upload;
  change and delete your own files), `documents.folders.manage` (folders,
  access, every file).
