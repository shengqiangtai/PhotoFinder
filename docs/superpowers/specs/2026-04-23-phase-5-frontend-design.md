# PhotoFinder Phase 5 Frontend Design

## Goal

Implement the architecture document's Phase 5 deliverables so the app feels like a complete product instead of an API demo. The frontend should provide a search-first single-page experience with a left control drawer, central results area, and right-side detail panel. It should support the full user flow: choose a folder, watch indexing progress, search photos, and inspect images without leaving the page.

## Scope

This spec covers only Phase 5:

- `web/index.html`
- `web/style.css`
- `web/app.js`
- `GET /api/system/qrcode`
- Tests required for the new backend endpoint
- Manual verification of the end-to-end UI flow

This spec does not cover Phase 6 packaging, README marketing content, or replacing the current Chinese query rewrite approach with a native multilingual embedding model.

## Product Direction

The homepage defaults to the main search view instead of a first-run wizard. First use is handled as an empty-library state inside the main application shell. This keeps the product centered on search even before content exists.

Folder import is handled inside the left-side control drawer rather than in a modal or full-screen onboarding step. Image inspection uses a right-side detail panel instead of a full-screen lightbox. These choices create a desktop-style workflow where searching, monitoring progress, and viewing photo details all happen in one continuous layout.

## Layout

The frontend uses a three-region shell:

1. Left control drawer
2. Central search and results stage
3. Right detail panel

### Left Control Drawer

The left drawer is a persistent control surface on desktop and a collapsible overlay on mobile. It contains four grouped cards:

- `Library`: current folders, add-folder action, counts
- `Models`: download status, model readiness, retry actions
- `Indexing`: current phase, progress bar, counts, speed
- `Device Access`: LAN URL and QR code for phone access

The drawer should feel like an intentional system console, not a generic settings menu.

### Central Stage

The center region is the visual focus of the page. It contains:

- The main search input
- A small subline for rewritten Chinese queries when applicable
- Lightweight search status and error messaging
- Empty-library state
- No-results state
- Responsive results grid

The search area remains visible in all non-fatal states. Indexing progress may appear in a compact banner near the top of this region, but it must not displace the main search experience.

### Right Detail Panel

The right panel is persistent on desktop and becomes a slide-up panel on mobile. It shows:

- Larger preview image
- Filename
- Taken time if available
- Full path
- Similarity when search results are active
- Open-original action

When nothing is selected, it shows a designed placeholder instead of staying empty.

## State Model

The frontend state is organized around a small set of top-level concerns:

- `systemInfo`
- `folders`
- `indexStatus`
- `downloadStatus`
- `searchQuery`
- `rewrittenQuery`
- `searchResults`
- `selectedPhoto`
- `ui` flags such as drawer/panel visibility and transient loading states

The state priority order is:

1. Fatal app error
2. Background task visibility such as indexing or model download
3. Content state such as empty library, no results, results present
4. Local interaction state such as selected card or open drawer

This ordering prevents transient UI actions from overriding important application status.

## Data Flow

### App Startup

On first load, the frontend requests these endpoints in parallel:

- `GET /api/system/info`
- `GET /api/library/folders`
- `GET /api/index/status`
- `GET /api/models/download/status`

The initial render then chooses between:

- Search-ready library state
- Empty-library guidance state
- Fatal backend-unavailable state

If indexing is already running, the frontend starts polling `GET /api/index/status`. If a model download is in progress, it starts polling `GET /api/models/download/status`.

### Folder Import

The add-folder action lives in the `Library` card in the left drawer. It triggers `GET /api/system/open-folder` and, if a path is returned, immediately posts that path to `POST /api/library/add`. Success refreshes folder data and begins index polling. Failure stays local to the drawer card and should not replace the entire page.

### Search

The main input uses a 250-300ms debounce. Non-empty queries call `GET /api/search`. The response updates:

- `searchResults`
- `rewrittenQuery`
- selection state when needed

If `rewritten_query` is present, the UI shows a small explanatory line under the input so users can see how Chinese terms were mapped into the CLIP search path.

### Selection and Detail Viewing

Clicking a result card sets `selectedPhoto`. The detail panel updates in place and does not navigate away from the page. The preview uses the thumbnail or full image route depending on the layout and desired fidelity. The original image action points to `/api/image/{id}`.

## Visual Direction

The interface should feel like a focused desktop photography tool rather than a generic admin dashboard.

- Use a bold, editorial layout with dark neutral surfaces and warm accent color rather than default purple or plain grayscale
- Keep typography deliberate and higher-contrast than the current placeholder page
- Use subtle gradients, panel depth, and staggered reveal motion
- Avoid decorative overload; motion should be meaningful and limited to panel transitions, card reveals, and progress updates
- Preserve usability on both desktop and mobile widths

The implementation should keep CSS variables centralized so the look can be tuned without rewriting component rules.

## Responsive Behavior

Desktop keeps all three regions visible when space allows. Tablet compresses widths but preserves the same mental model. Mobile changes the shell without changing the workflow:

- Left drawer becomes a top-left button that opens an overlay drawer
- Right detail panel becomes a bottom sheet or full-width overlay panel
- Results grid reduces column count and padding
- Search remains fixed near the top for quick iteration

The app should remain usable on phones without requiring a separate mobile design.

## Error Handling

### Fatal Errors

If startup requests fail in a way that prevents the application from functioning, the center area shows a full fatal error state with a retry action.

### Non-Fatal Errors

- Search failure: preserve prior results and show a compact inline error
- Add-folder failure: show error inside the `Library` card
- Open-folder failure: show that GUI selection is unavailable in the current environment
- Model download failure: show the reason and a retry action in the `Models` card
- Image load failure: degrade only the affected image tile or detail preview

Errors should stay local when possible. The application should avoid blocking alerts for routine failures.

## Backend Addition

Phase 5 requires one backend addition:

- `GET /api/system/qrcode`

This route returns a PNG image representing the LAN URL already exposed by `GET /api/system/info`. It is used by the `Device Access` card so a phone on the same network can open the web app quickly.

If a LAN URL cannot be determined, the route should return a meaningful API error rather than an empty image.

## Frontend File Boundaries

### `web/index.html`

Defines the application shell, static placeholders, and semantic containers for:

- left drawer
- central search stage
- right detail panel
- reusable empty/error/loading sections

It should not contain large inline styles or large inline behavior blocks.

### `web/style.css`

Owns the complete visual system, including:

- design tokens
- layout grid
- drawer/panel styling
- card styling
- result grid
- responsive breakpoints
- transition and motion rules

### `web/app.js`

Owns:

- state container
- API client helpers
- render functions for each major region
- debounce and polling logic
- event wiring
- UI state transitions

The JavaScript should stay framework-free and modular enough that rendering logic is understandable by file section.

## Testing Strategy

Automated tests stay narrow in Phase 5:

- add backend tests for `GET /api/system/qrcode`
- keep existing API tests green

The frontend itself is verified through manual acceptance instead of introducing a new browser test stack in this phase.

Manual verification covers:

- startup into the main search shell
- empty-library state
- add-folder from the left drawer
- indexing progress updates without page changes
- search result refresh
- Chinese rewritten-query hint display
- selecting a photo and updating the right detail panel
- mobile-width drawer and detail panel behavior

## Acceptance Criteria

Phase 5 is complete when:

- the placeholder page is replaced with a functional single-page UI
- the default landing view is the main search shell
- folder import is accessible from the left drawer
- indexing and model download progress are visible in the app
- search results render in a responsive grid
- clicking a result updates the right detail panel
- `rewritten_query` is surfaced when Chinese search uses the rewrite path
- `/api/system/qrcode` returns a usable PNG for the LAN URL
- the documented product flow is manually verified:
  select folder -> build index -> search -> inspect image

## Spec Self-Review

- Placeholder scan: no TODO/TBD markers remain
- Consistency: layout, state model, and backend additions align with the Phase 5 scope only
- Scope check: packaging and release work remain in Phase 6 and are intentionally excluded
- Ambiguity check: the default home state, import location, and detail-view interaction are all explicit
