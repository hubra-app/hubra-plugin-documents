# Documents

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
