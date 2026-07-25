# hide_and_seek

Static map toolkit for a hide-and-seek ruleset in Greater Copenhagen.

The project contains:
- a Leaflet-based interactive map
- a printable A3 map export
- Python preprocessing scripts that generate optimized static GeoJSON data for the web app

## Quick Start

### 1. Prerequisites

- Python 3.12+
- Node.js 20+
- npm
- uv: https://docs.astral.sh/uv/

### 2. Install dependencies

```bash
uv sync
npm install
```

### 3. Run the app locally

```bash
npm run dev
```

Open the URL shown by Vite (typically http://127.0.0.1:5173).

### 4. Build production assets

```bash
npm run build
```

This builds the static site to dist and generates print-map.pdf.

### 5. Run tests

```bash
uv run pytest
npm test
```

If Playwright browsers are missing:

```bash
npx playwright install --with-deps chromium
```

## Developer Workflow

### Rebuild datasets

Run preprocessing when data rules or sources change:

```bash
npm run build:data
```

This executes scripts/build_data.py and writes output to:
- data/derived/
- web/public/data/

### Preview production bundle

```bash
npm run preview
```

### Capture screenshots and print output

In one terminal:

```bash
npm run preview -- --host 127.0.0.1 --port 4173
```

In another terminal:

```bash
npm run capture
```

Output files:
- test-results/captures/interactive-map.png
- test-results/captures/print-map.png
- test-results/captures/print-map.pdf

## Project Structure

- scripts: preprocessing and output capture scripts
- src/hide_and_seek: Python gameplay rules used by preprocessing
- tests: Python unit tests
- web: HTML, JS, and CSS application source
- web/public/data: committed static runtime datasets
- web-tests: Playwright end-to-end tests
- docs: dataset notes and implementation documentation

## Data Pipeline

### Data sources downloaded by preprocessing

Main pipeline in scripts/build_data.py downloads and uses:
- Rejseplanen GTFS ZIP
- Dataforsyningen kommuner
- Dataforsyningen postnumre
- Dataforsyningen opstillingskredse
- Dataforsyningen sogne
- Dataforsyningen afstemningsomraader

### Processing steps

1. Read the committed Copenhagen playable-area boundary.
2. Load GTFS routes/trips/stop_times/stops/shapes.
3. Keep bus service and Saturday service combinations relevant to the ruleset.
4. Filter stops to boundary interior.
5. Compute time-window stop activity.
6. Mark eligible stops from nearby event density and per-hour service checks.
7. Keep routes that contain consecutive eligible stops.
8. Clip/simplify administrative overlays to the playable boundary.
9. Write deterministic GeoJSON/JSON output to both data/derived and web/public/data.

### Where processed files are stored

- data/derived: pipeline outputs for inspection and reproducibility
- web/public/data: runtime data consumed by the frontend and included in site builds

## Frontend Architecture

### Entry pages

- web/index.html: main interactive map
- web/print.html: print-focused map layout and legend
- web/where-am-i.html: administrative lookup page
- web/guide.html: game guide and allowed stations page

### Main modules

- web/src/main.js: interactive map initialization and overlay coordination
- web/src/shared.js: common map/data helpers
- web/src/metro.js and web/src/stog.js: transport layers and station interactions
- web/src/AdministrativeLayer.js and web/src/LabelManager.js: overlay boundaries and label rendering
- web/src/AdministrativeLookup.js and web/src/PolygonLookup.js: point-in-polygon lookup path
- web/src/WhereAmIPage.js and web/src/GuidePage.js: page-specific application logic

### Administrative overlay system

The map overlays are configured in web/src/main.js as ADMIN_LAYER_CONFIGS.
Each config defines:
- dataset file
- boundary style
- label source field
- popup summary field
- label visibility thresholds

AdministrativeLayer couples boundary rendering with zoom-sensitive labels.

## Performance and Data Optimization

The pipeline clips and simplifies every dataset to the playable boundary before writing runtime files. The browser receives no nationwide administrative or transit dataset.

Remaining performance work:

1. Build spatial indexes for polygon lookup in preprocessing
- Why: reduces runtime point-in-polygon checks to a smaller candidate set.
- Impact: High
- Effort: Medium

2. Persist bbox arrays per feature in output GeoJSON properties
- Why: avoids runtime bounds recomputation in lookup modules.
- Impact: Medium
- Effort: Small

3. Clip transit geometries to boundary with an additional small pad
- Why: further reduces geometry complexity outside playable area.
- Impact: Medium
- Effort: Small

4. Optional topology-preserving simplification by zoom tier
- Why: lighter payload and faster rendering on mobile.
- Impact: Medium
- Effort: Medium

5. Split guide-only datasets from map-critical datasets
- Why: lets first paint load only essentials.
- Impact: Low to Medium
- Effort: Medium

6. Precompute per-layer name indexes for administrative lookups
- Why: removes repeated string/property access in hot paths.
- Impact: Low
- Effort: Small

## Dependency Notes

Current runtime dependency footprint is intentionally small:
- leaflet

Dev/test/build dependencies:
- vite
- @playwright/test

Python dependencies are limited to preprocessing and tests.

## Configuration and Build Files

These files control build, preprocessing, deployment, and hosting behavior:

- package.json: npm scripts for dev/build/test/data pipeline orchestration
- pyproject.toml: Python project metadata and dependencies
- uv.lock: pinned Python dependency lockfile
- playwright.config.js: E2E test targets and preview web server
- web/vite.config.js: multi-page static build configuration and output directory
- scripts/build_data.py: primary data preprocessing pipeline
- scripts/build_metro_data.py: metro line/station extraction utility
- scripts/build_s_tog_data.py: S-tog line/station extraction utility
- scripts/build_print_pdf.mjs: PDF generation from built print page
- .github/workflows/deploy-pages.yml: GitHub Pages CI build and deploy workflow

## Deploying to GitHub Pages

### Prerequisites

- GitHub repository with Actions enabled
- GitHub Pages configured to use GitHub Actions as the source
- Required files committed, including web/public/data and the workflow file

### Required repository settings

In GitHub repository settings:
1. Go to Pages.
2. Set Source to GitHub Actions.

### Deployment workflow

Deployment is controlled by .github/workflows/deploy-pages.yml.

Current trigger:
- push to branch main or master
- manual run via workflow_dispatch

The workflow:
1. Checks out code.
2. Installs Python/uv and Node dependencies.
3. Installs Playwright Chromium.
4. Runs npm run build.
5. Uploads dist as Pages artifact.
6. Deploys via actions/deploy-pages.

### Build command used for deployment

```bash
npm run build
```

### How to publish a new version

1. Ensure local pipeline/tests pass.
2. Commit and push to the deployment branch used by the workflow trigger.
3. Wait for Deploy GitHub Pages workflow to complete.

### How to verify deployment

1. Open the Actions tab and confirm build and deploy jobs succeeded.
2. Open the published Pages URL shown in the deploy job environment output.
3. Verify index, print, guide, and where-am-i pages load.

### Published site URL pattern

For repo owner/repo:
- https://owner.github.io/repo/

## Troubleshooting

### App loads but data is missing

- Verify web/public/data contains expected GeoJSON/JSON files.
- Re-run npm run build:data.

### Browser tests fail immediately

- Install Playwright browser binaries:
  npx playwright install --with-deps chromium

### Python imports fail in tests

- Re-run uv sync to restore environment.
- Confirm tests use uv run pytest.

## Adding New Datasets

Recommended process:
1. Add a downloader/loader step in scripts/build_data.py.
2. Filter to the playable boundary during preprocessing.
3. Simplify geometry before writing output.
4. Write output to data/derived and web/public/data.
5. Add a dedicated loader in web/src only if the dataset is needed at runtime.
6. Add or update tests and docs.

Keep nationwide data out of runtime payloads unless clipped and needed inside the playable area.
