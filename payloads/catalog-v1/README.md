# Typed payload catalog (version 1)

Initialize the private index with `repel catalog init`, then use `repel catalog add`
or `repel generate --catalog payloads/catalog-v1 --register-prefix NAME`.

- `catalog.json`: layout/version descriptor.
- `catalog.sqlite3`: private, transactional ID/tag/type index.
- `entries/source/<language>/<id>.json`: source metadata.
- `entries/document/<document-type>/<id>.json`: document metadata.
- `entries/data/plain/<id>.json`: generic text metadata.
- `objects/sha256/<first-two-hash-characters>/<sha256>`: immutable UTF-8 bytes.

The SQLite index, entries, and content objects are local operational data and ignored
by Git. No existing payload collection is automatically migrated or scanned.
See ../../docs/catalog-deployment.md for generation, deployment, and exact recovery.
