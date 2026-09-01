# Local AI Console Web

This is the Windows Controller web foundation for Local AI Console. It uses React, TypeScript, and Vite to provide a desktop-first application shell, browser navigation, safe Controller metadata views, and a Prompt Workbench placeholder.

It does not provide chat, prompt generation, persistence, model controls, Node Agent connectivity, authentication, or third-party integrations.

## Development

Install the locked dependencies from this directory:

```powershell
npm ci
```

Start the Control API separately on the local development machine, then start Vite:

```powershell
npm run dev
```

During development, browser requests to `/api/*` are proxied to `http://127.0.0.1:8000`. This keeps the initial local development setup same-origin without introducing a production CORS architecture. The proxy target is deliberately a generic loopback address; do not replace it with private network or host information in committed files.

Run the checks:

```powershell
npm test
npm run typecheck
npm run build
```

## Deployment note

The production host must serve the built single-page application with an SPA fallback so direct navigation or refresh on routes such as `/tools/prompt-workbench` resolves to `index.html`.

## Public configuration boundary

Any `VITE_*` value is embedded in browser-visible frontend code. Never place secrets, credentials, private host details, model paths, tokens, or personal data in a `VITE_*` variable. This repository contains code and sanitized templates only; private runtime data remains outside the repository under the existing runtime boundary.
