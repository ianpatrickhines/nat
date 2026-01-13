# Nat Chrome Extension

## Architecture

- **Manifest V3** - Required for Chrome Web Store
- **Vite** - Build tooling with Preact plugin
- **Preact** - Lightweight React alternative (3kb gzipped)
- **TypeScript** - Strict mode enabled

## Directory Structure

```
extension/
├── src/
│   ├── background/     # Service worker (Manifest V3)
│   │   └── index.ts    # Auth state, message passing
│   ├── content/        # Content script (injected into NB pages)
│   │   ├── index.tsx   # Entry point, renders Sidebar
│   │   └── content.css # Scoped styles
│   ├── components/     # Preact components
│   │   └── Sidebar.tsx # Main sidebar UI
│   ├── hooks/          # Custom Preact hooks
│   └── utils/          # Utility functions
├── public/
│   └── manifest.json   # Extension manifest
├── dist/               # Build output (gitignored)
└── vite.config.ts      # Build configuration
```

## Build Commands

```bash
npm run dev       # Watch mode for development
npm run build     # Production build
npm run typecheck # TypeScript check
```

## Key Patterns

### Content Script Isolation
- CSS scoped to `#nat-sidebar-root` with maximum z-index
- Container uses `all: initial` to reset inherited styles
- Sidebar width: 350px when open, 40px when collapsed

### Background Service Worker
- No persistent state (Manifest V3 limitation)
- Uses chrome.storage.local for auth state
- Message passing with content scripts

### Message Types
- `GET_AUTH_STATE` - Get current auth from storage
- `SET_AUTH_STATE` - Store auth token and user info
- `CLEAR_AUTH_STATE` - Logout/clear stored auth
- `TOGGLE_SIDEBAR` - Toggle sidebar visibility from toolbar icon

## Host Permissions
Extension only runs on `*.nationbuilder.com` domains.

## Testing in Chrome
1. Run `npm run build`
2. Go to `chrome://extensions`
3. Enable "Developer mode"
4. Click "Load unpacked"
5. Select the `extension/dist` folder
