# hide_and_seek-randers

<!-- TODO: This repo is currently Randers-focused. Replace or parameterize
	Randers references when switching to Storkøbenhavn or another region. -->

Randers hide-and-seek helper tools:

- interactive web map
- printable map
- one-off transit/admin preprocessing for static deployment

## Main features

- old Randers municipality boundary as game area
- bus routes and valid stops for the chosen ruleset
- address lookup via DAWA
- GPS lookup in browser
- sogn overlay
- afstemningsområde lookup + overlay
- GitHub Pages deployment

## Tech stack

- Python via `uv`
- JavaScript via `npm`
- Leaflet for mapping
- Playwright for browser tests

## Local setup

Install dependencies:

```bash
uv sync
npm install
```

## Rebuild derived data

Run when transit/admin rules or preprocessing code changes:

```bash
uv run python scripts/build_data.py
```

This updates the derived files used by the web app in `web/public/data/`.

## Run locally

Start the interactive app:

```bash
npm run dev
```

Then open the local Vite URL, usually:

```text
http://localhost:5173
```

## Production build

```bash
npm run build
npm run preview
```

`npm run build` now does two things:

- builds the static site into `dist/`
- generates an updated portrait `print-map.pdf`

The PDF is written to:

- `dist/print-map.pdf`
- `web/public/print-map.pdf`

## Tests

Python tests:

```bash
uv run pytest
```

Browser tests:

```bash
npm test
```

The Playwright suite covers:

- desktop + phone layouts
- page load
- real address lookup
- real browser geolocation
- phone stop tapping

## Capture screenshots / print output

Start preview in one terminal:

```bash
npm run preview
```

Then in another terminal:

```bash
npm run capture
```

Outputs are written to:

- `test-results/captures/interactive-map.png`
- `test-results/captures/print-map.png`
- `test-results/captures/print-map.pdf`

## Deployment

This repo deploys to GitHub Pages via GitHub Actions.

Published site:

```text
https://soetang.github.io/hide_and_seek-randers/
```

The Pages workflow builds from the committed derived data already stored in `web/public/data/`.

## Important project note

Some raw source files used during development may be local-only and are not required for GitHub Pages deployment.

For deployment, the important committed artifacts are the derived static data files in:

```text
web/public/data/
```

## Repo structure

- `scripts/` — preprocessing and capture scripts
- `src/hide_and_seek/` — Python helpers/rules
- `tests/` — Python tests
- `web/` — web app source
- `web/public/data/` — committed derived data for deployment
- `web-tests/` — Playwright tests
- `docs/` — research and planning docs
