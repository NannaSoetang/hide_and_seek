# Midttrafik fare zones

## Overview

<!-- TODO: Midttrafik notes reference Randers; update when adapting to a different region -->
I did **not** find a clearly documented, openly reusable machine-readable Midttrafik fare-zone dataset for Randers.

What is clearly available is official **reference material** such as zone maps, interactive viewers, route pages, and journey-planning tools.

## Available source / material

- Midttrafik route and zone map pages
- Midttrafik interactive route/zone viewer
- Randers route pages and PDFs
- Rejseplanen trip planning for trip-specific zone/pricing checks

## How we could use it

- Treat Midttrafik/Rejseplanen as an official reference source
- Link to the official viewer if needed
- Potentially create a small project-maintained fallback later, but only if absolutely necessary

## Licensing / attribution

No clear open-data reuse license was found for zone geometry.

Safest assumption: these materials are official references, **not** an openly reusable dataset.

## Risks / open questions

- Interactive map layers may exist behind the viewer, but no documented reusable dataset was found
- Reverse-engineering zone geometry would create legal and maintenance risk
- This layer may not be worth the complexity for v1

## Recommendation for this project

Treat fare zones as **optional and unresolved**.

Do not build the first version around fare-zone polygons unless Midttrafik provides a documented reusable dataset or explicit permission.
