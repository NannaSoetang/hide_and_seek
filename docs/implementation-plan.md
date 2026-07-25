# Implementation plan

## Goal

<!-- TODO: This plan is Randers-specific. Consider generalizing steps or
   making the boundary/kommunekode configurable for other regions. -->

Build two assets for a Randers Jet Lag: Hide and Seek game:

1. a **printable map** of the playable area and bus network
2. a **mobile-friendly interactive web map** that can identify the current **sogn** from GPS or typed address and optionally show other area layers

The project should rely on **one-off preprocessing** and ship **derived static data**, so the deployed web app does not depend on live heavy data fetches for its core logic.

## Locked product decisions

### Play area
- Use the **old Randers municipality boundary (2006 kommunegrænse)**
- This is the legal game boundary
- The web app should simply report **outside area** if a searched or GPS location is not inside it

### Printable map
- Mandatory deliverable
- Utility-first design
- Show:
  - old Randers boundary
  - included bus routes
  - only **eligible stops**
  - names for **major eligible stops**
  - route numbers and symbols
- Do **not** show parish boundaries on print
- Should be printable at **A3**, with portrait/landscape chosen from final geometry

### Interactive map
- Static **HTML/CSS/JS** hosted on **GitHub Pages**
- Mobile-first, especially modern iPhone Safari
- Should support:
  - GPS lookup on load
  - typed address search
  - current parish highlight
  - parish overlay
  - optional overlays for `postnummer` and `opstillingskreds`
- Only one optional area layer should be active at a time

### Bus rules
- Include **city buses and regional buses** equally
- Stop eligibility rule:
  - use **pure event count**
  - count both directions together
  - use **normal Saturday** service
  - evaluate the **09:00–18:00** play window
  - stop must average at least **2 bus stop events per hour**
- Route inclusion rule:
  - route must have at least **2 usable consecutive in-zone eligible stops**
  - both stops must themselves be eligible
- Stops outside the legal boundary are excluded
- If official route geometry becomes unusable, fallback is:
  1. OSM route geometry if available
  2. stop-to-stop lines otherwise

### Tooling
- Python via **`uv`**
- JavaScript via **`npm`**

## Recommended technical architecture

### Data pipeline
Use **Python** for one-off preprocessing and analysis.

Recommended responsibilities:
- download raw source datasets
- extract only Randers-relevant records
- compute stop eligibility and route inclusion
- simplify geometries for web/print use
- write small derived JSON/GeoJSON/TopoJSON files for the app

### Web app
Use a **static Leaflet app** with local derived data files.

Why:
- simplest GitHub Pages deployment
- good fit for mobile Safari
- enough for polygon overlays and route/stops display
- easier than a WebGL/vector-tile-first stack

### Print generation
Use the same derived data as the web app, but render a dedicated print layout.

Likely approach:
- dedicated print HTML page or export-oriented map view
- browser print-to-PDF for final PDF output
- ensure route/stops/boundary remain readable without needing live basemap access

## Instructions for the implementation agent

The implementation agent should follow these rules while building:

1. **Do the work incrementally**
   - complete one layer of the system at a time
   - keep the app runnable after each meaningful step

2. **Prefer derived static data over live runtime dependencies**
   - download and preprocess source datasets one-off
   - keep the deployed app dependent only on local derived files wherever possible

3. **Use the agreed tooling**
   - Python environments and packages via `uv`
   - JavaScript tooling and packages via `npm`

4. **Verify each phase before moving on**
   - do not build several large pieces blindly
   - after each phase, run the relevant validation checks listed below

5. **Keep data processing reproducible**
   - scripts should be rerunnable
   - outputs should be deterministic enough that regenerated derived data is inspectable

6. **Avoid making DAWA a hard long-term dependency**
   - if DAWA is used initially, isolate it behind a small search adapter or service wrapper

7. **Do not treat fare zones as critical path**
   - complete the playable boundary, parish lookup, and transit eligibility first

8. **Keep route logic faithful to the agreed game rules**
   - stop eligibility and route inclusion rules are product rules, not implementation details

## Verification and testing during implementation

The implementation agent should test continuously, not only at the end.

### After environment setup
- verify Python commands run through `uv`
- verify JS tooling installs through `npm`
- verify the project has a documented command for:
  - preprocessing data
  - running the local web app
  - running tests

### After boundary extraction
- confirm the old Randers boundary file exists
- inspect geometry bounds and feature count
- render the boundary alone on a simple map page and visually confirm it matches expectations
- test a few hand-picked inside/outside coordinates

### After GTFS ingestion
- verify expected GTFS files are present and readable
- verify row counts are non-zero for `stops`, `trips`, `stop_times`, `routes`, and `shapes`
- verify Randers-area filtering leaves plausible numbers of stops/routes
- log a small human-readable summary of agencies, routes, and stop counts

### After stop-eligibility calculation
- write tests for the eligibility function
- verify sample stops manually from GTFS source rows
- confirm the averaging window is exactly the agreed Saturday 09:00–18:00 logic
- confirm directions are counted together
- confirm stops outside the boundary are excluded

### After route-inclusion calculation
- write tests for the route inclusion rule
- verify a sample included route really has 2 consecutive in-zone eligible stops
- verify a sample excluded route fails for the expected reason
- confirm route numbers in output are stable and readable

### After area-layer preprocessing
- verify each layer file loads successfully
- verify feature counts are plausible
- verify point-in-polygon lookup returns results for known sample points
- verify geometry simplification did not create obvious broken polygons

### After implementing parish lookup in the web app
- test GPS flow with mocked or manual coordinates
- test typed address flow with known addresses
- test outside-area behavior explicitly
- test several known points against expected `sogn`
- confirm the UI highlights the resolved parish correctly

### After implementing bus overlays in the web app
- verify only eligible stops are shown
- verify included routes render correctly
- verify tapping a route reveals its route number if implemented that way
- check mobile performance with all active default layers

### After printable map implementation
- verify all required elements are present:
  - boundary
  - included routes
  - eligible stops
  - major stop labels
  - route legend
- export a PDF and inspect readability
- ideally perform one physical print test

### Before final handoff
- run all automated tests
- rerun the preprocessing pipeline from scratch
- rebuild the web app from clean state
- verify the generated derived data matches expectations
- test the final app locally in a production-like static serving mode

## Suggested test categories

### Python tests
- geometry clipping helpers
- point-in-polygon lookup helpers
- GTFS Saturday service filtering
- stop eligibility computation
- route inclusion computation
- data export schema checks

### JavaScript tests
- lookup-state helpers
- outside-area decision logic
- layer-selection logic
- result formatting logic

### Manual integration tests
- known address inside area
- known address outside area
- known GPS coordinate inside area
- known GPS coordinate outside area
- sample eligible stop appears on map
- sample ineligible stop does not appear
- sample included route appears
- sample excluded route does not appear

## Suggested quality gates

The implementation agent should not move to the next major phase until these gates pass:

1. **Boundary gate**
   - old Randers boundary renders correctly
   - inside/outside checks work on sample points

2. **Transit gate**
   - eligible stops and included routes are generated
   - sample cases are manually verified

3. **Parish gate**
   - known sample points resolve to expected `sogn`
   - outside-area behavior is correct

4. **Web app gate**
   - app loads on mobile Safari
   - map interactions are usable
   - layer switching works

5. **Print gate**
   - A3 PDF is readable
   - required information is visible without zooming

## Dataset plan

### 1. Rejseplanen GTFS
Primary source for transit logic.

Use it for:
- stop coordinates
- route IDs
- trip/stop timing
- Saturday service filtering
- route geometry from `shapes.txt`

Needed files:
- `stops.txt`
- `stop_times.txt`
- `trips.txt`
- `calendar.txt`
- `calendar_dates.txt`
- `routes.txt`
- `shapes.txt`
- `agency.txt`

### 2. Historical DAGI municipality boundary
Primary source for the legal play area.

Use it to:
- extract the old Randers 2006 boundary
- clip/filter stops and routes
- decide whether locations are inside or outside the game area

### 3. DAGI Sogneinddeling
Primary source for parish lookup.

Use it to:
- determine current parish from GPS/search result
- render parish overlay in the interactive map

### 4. DAGI Postnummerinddeling
Optional comparison layer for the interactive map.

### 5. DAGI Opstillingskreds
Optional comparison layer for the interactive map.

### 6. DAWA address search
Temporary address-search candidate.

Use only if acceptable despite lifecycle risk.
The app should be structured so the search provider can be swapped later.

### 7. Fare zones
Treat as unresolved/optional.
Do not block v1 on this dataset.

## Derived data outputs

Recommended derived files:

- `old-randers-boundary.geojson`
- `sogne.geojson` or simplified equivalent
- `postnumre.geojson` or simplified equivalent
- `opstillingskredse.geojson` or simplified equivalent
- `eligible-stops.geojson`
- `included-routes.geojson`
- `route-stop-summary.json`
- `lookup-index.json` if useful for lightweight UI logic

Only derived data should be committed.

## Processing plan

### Phase 1: boundary setup
1. Acquire historical Randers 2006 municipality boundary
2. Verify polygon manually
3. Convert to project CRS/format
4. Save simplified derived boundary file

### Phase 2: transit preprocessing
1. Download Rejseplanen GTFS ZIP
2. Load relevant GTFS tables
3. Filter to bus services relevant to Randers
4. Identify stops inside old Randers boundary
5. For a normal Saturday, compute stop-event counts in the 09:00–18:00 window
6. Mark stops as eligible if average events/hour >= 2
7. Keep routes only if they have at least 2 consecutive in-zone eligible stops
8. Derive representative route geometry
9. Export eligible stops and included routes

### Phase 3: admin-layer preprocessing
1. Download current `sogn`, `postnummer`, and `opstillingskreds` geometries
2. Clip to relevant extent around Randers
3. Simplify geometry for mobile use
4. Export web-friendly derived files

### Phase 4: interactive app
1. Build static Leaflet app
2. Load derived data locally
3. Add GPS lookup flow
4. Add typed address search flow
5. Run point-in-polygon lookup against old Randers boundary
6. If inside area, resolve and display `sogn`
7. Add optional area-layer switcher
8. Add bus route and eligible stop overlays
9. Add attribution and source notes

### Phase 5: printable map
1. Create print-focused layout using same derived data
2. Tune route styling and stop labeling for A3 readability
3. Label major eligible stops
4. Add game-boundary note and route legend
5. Export print-ready PDF

## Lookup behavior plan

### GPS
- Ask for browser geolocation on load
- If the point is outside the old Randers boundary, show only **outside area**
- If inside, resolve current `sogn`

### Address search
- Search wider than the play area
- On selection, convert to coordinates
- If outside boundary, show **outside area**
- If inside boundary, resolve `sogn`

## Validation plan

### Boundary validation
- verify the 2006 boundary visually against official historical material
- check a few known edge locations inside/outside

### Transit validation
- inspect a sample of included routes manually
- inspect a sample of eligible and ineligible stops manually
- check that each included route really has at least 2 consecutive in-zone eligible stops
- verify stop counts against GTFS rows for sample cases

### Parish validation
- prepare 10–20 known Randers addresses/places
- compare resolved parish against official source behavior/manual expectation
- test boundary-edge locations where parish assignment could be ambiguous

### Printable map validation
- manual inspection checklist:
  - legal boundary clearly visible
  - route lines readable
  - major eligible stops readable
  - enough empty space to annotate by hand
  - legend understandable
- ideally do at least one real A3 test print

### Mobile validation
- test on iPhone Safari
- confirm GPS permission flow
- confirm touch targets and map movement
- confirm acceptable loading time with local derived files

## Deployment plan

### Local development
- Python environment with `uv`
- JavaScript dependencies with `npm`
- preprocessing scripts run locally to regenerate derived data

### Hosting
- host the static app on **GitHub Pages**
- avoid server dependencies
- avoid runtime dependence on large external APIs for map logic

## Recommended implementation order

1. historical boundary extraction
2. GTFS stop eligibility analysis
3. route filtering and geometry export
4. parish layer preprocessing
5. minimal interactive parish lookup app
6. bus overlays in web app
7. printable map layout
8. optional postnummer/opstillingskreds layers
9. optional fare-zone investigation if still needed

## Main risks

### 1. Historical boundary access details
Need to confirm the exact historical DAGI extraction method.

### 2. DAWA lifecycle risk
DAWA is not a safe long-term dependency, so search should be isolated behind a replaceable adapter.

### 3. Route geometry complexity
GTFS shapes may require route/direction/branch decisions before producing a clean map.

### 4. Fare-zone uncertainty
Fare zones should not be part of the critical path.

## Success criteria

The project is successful when:

- the playable boundary is correct and visible
- the printable map is usable for real gameplay
- the web app correctly says **outside area** or shows the current **sogn**
- the transit overlay includes only stops and routes that satisfy the agreed gameplay rules
- the whole system can be regenerated from one-off preprocessing without relying on live heavy backend services
