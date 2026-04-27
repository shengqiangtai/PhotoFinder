# PhotoFinder Phase 2 Design

## Scope

Phase 2 implements the architecture document's "扫描与元数据" stage so the app can import one or more photo folders, scan supported image files, extract metadata, persist photo rows with `has_vector=0`, and expose the minimum library/system APIs needed to observe the imported state.

This phase does not implement embedding, indexing progress, search, thumbnails-as-index-artifacts, model download, or full frontend state handling. The acceptance target is the architecture document's Phase 2 requirement: after adding a folder through the API, the `photos` table contains records with `has_vector=0`.

## Architecture

The implementation stays aligned with the document's layer boundaries:

- `utils/image_utils.py` handles safe image loading, EXIF date extraction, and thumbnail generation helpers.
- `core/scanner.py` only scans the filesystem and computes file diffs against current DB state.
- `api/routes/library.py` validates requests, persists folder records, and schedules background import work.
- `api/routes/system.py` exposes runtime/system information and the GUI-backed folder picker.
- `api/schemas.py` defines request/response models used by Phase 2 routes.
- `utils/network_utils.py` resolves the LAN URL for `system/info`.

The existing `db/database.py` remains the async DB access layer. Route handlers and background tasks use it directly rather than adding a new service layer in this phase.

## Data Flow

### Add Folder

1. `POST /api/library/add` receives a folder path.
2. The handler normalizes the path, verifies it exists and is a directory, then upserts it into `folders`.
3. The handler returns immediately with `folder_id`, `path`, and `status="scanning_started"`.
4. A background task scans the folder and imports metadata.

### Background Import

1. `core.scanner.scan_folder(folder_path)` recursively scans the directory tree.
2. The scanner ignores hidden files/directories and known junk entries such as `__MACOSX`, `@eaDir`, and `Thumbs.db`.
3. The scanner compares discovered files against the DB records already associated with that folder and returns:
   - `new_files`
   - `modified_files`
   - `deleted_files`
   - `total_found`
4. The background importer:
   - inserts new photos
   - updates modified photos
   - deletes removed photos
   - resets `has_vector=0` for changed files
   - clears stale `error_msg` on successful metadata refresh
5. `folders.last_scan` and `folders.photo_count` are updated after the import completes.

### Folder Listing

`GET /api/library/folders` aggregates folder statistics from `folders` and `photos`, including `indexed_count` as the count of rows where `has_vector=1`.

### System Info

`GET /api/system/info` reports:

- app version
- placeholder model status values for later phases
- total photo count
- indexed photo count
- DB size in MB
- LAN URL from `utils.network_utils.get_lan_ip()`
- `first_run` from `app_config`

### Open Folder Dialog

`GET /api/system/open-folder` opens a native folder picker via `tkinter.filedialog.askdirectory()`. If `tkinter` is unavailable, the GUI cannot initialize, or the dialog fails, the API returns an error rather than silently falling back to a query parameter path.

## Module Details

### `utils/image_utils.py`

- `read_image_safe(path: str) -> Image.Image`
  - opens common image formats with Pillow
  - applies `ImageOps.exif_transpose()` to normalize orientation
  - converts deferred file handles into an in-memory copy so callers can safely use the returned image after the file is closed
  - if `pillow-heif` is installed, registers HEIF support on import
  - raises a descriptive exception on unreadable/damaged files
- `generate_thumbnail(path: str, size: int = 256) -> bytes`
  - loads the image through `read_image_safe`
  - resizes proportionally to fit within the target square
  - writes JPEG bytes
- `extract_exif_date(path: str) -> Optional[str]`
  - reads EXIF `DateTimeOriginal`, then `DateTimeDigitized`, then `DateTime`
  - converts `YYYY:MM:DD HH:MM:SS` to ISO8601
  - returns `None` when metadata is missing or invalid

RAW support is intentionally best-effort in this phase. With the current dependency set, unsupported RAW files are recorded as import errors instead of adding another image stack now.

### `core/scanner.py`

- Defines `ScanResult` as a dataclass.
- Uses `os.scandir()` recursion for better performance than `os.walk()`.
- Filters by `config.SUPPORTED_EXTENSIONS`.
- Builds a `{path: mtime}` map for current filesystem entries and compares it to DB rows for the folder.
- Treats an mtime change as "modified".

The scanner does not extract image metadata or write the DB. It stays focused on filesystem discovery and diffing.

### `api/routes/library.py`

- `POST /api/library/add`
  - validates path
  - upserts folder row
  - schedules background import
  - returns accepted response
- `GET /api/library/folders`
  - returns all active folders ordered by most recently added

Background import work lives in this module in Phase 2 to avoid introducing a premature orchestration layer before Phase 3's dedicated indexer exists.

### `api/routes/system.py`

- `GET /api/system/info`
  - uses DB aggregates and config values
- `GET /api/system/open-folder`
  - wraps the native picker
  - returns `{ "selected_path": ... }` or `{ "cancelled": true }`
  - raises HTTP 500 when the picker cannot be opened

### `api/schemas.py`

Phase 2 schemas:

- `AddFolderRequest`
- `AddFolderResponse`
- `FolderResponse`
- `FolderListResponse`
- `SystemInfoResponse`
- `OpenFolderResponse`

## App Wiring

`api/app.py` is extended to include route modules for `library` and `system`. Phase 1's root redirect and static mount stay unchanged.

`main.py` remains the single entrypoint. No startup sequence changes are needed beyond using the expanded API app.

## Error Handling

- Invalid folder path: `400 Bad Request`
- Existing folder re-add: reuse existing row and rescan in background instead of failing
- Unreadable individual image: record the error in `photos.error_msg`, continue processing the rest
- Folder picker unavailable: `500 Internal Server Error`
- No LAN IP available: `lan_url` is `null`

The importer should never abort the whole folder because one image fails.

## Testing Strategy

Phase 2 verification adds focused tests for:

1. image utility behavior with a generated local image
2. scanner diff detection for new/modified/deleted files
3. `POST /api/library/add` importing photo metadata into SQLite with `has_vector=0`
4. `GET /api/library/folders` returning folder statistics
5. `GET /api/system/info` returning a stable structure
6. `GET /api/system/open-folder` success and failure behavior via mocks

Tests use temporary directories and generated images so they do not depend on external fixtures.

## Self-Review

- Placeholder scan: no TODO/TBD placeholders remain.
- Consistency: background import writes metadata only and leaves vector generation for Phase 3, matching the staged architecture.
- Scope: limited to the architecture document's Phase 2 deliverables.
- Ambiguity resolution: RAW support is explicitly best-effort with recorded errors under the current dependency set.
