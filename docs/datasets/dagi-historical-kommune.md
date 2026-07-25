# DAGI historical kommune boundary

## Overview

<!-- TODO: This dataset note references Randers specifically; update extraction
	guidance when changing the target region. -->

The old Randers municipality boundary should come from the **historical DAGI municipality dataset**, not the current DAWA municipality endpoint.

The goal is to extract the pre-reform Randers municipality polygon valid in **2006**.

## Relevant fields / data model

Expected useful concepts in the historical DAGI model:

- municipality identity (`kode`, `DAGIid`, `navn`)
- temporal validity fields
- registration/history metadata
- polygon geometry

The current Randers municipality code to verify against is `0730`, but the exact historical schema should be checked in the historical service metadata.

## How to extract old Randers 2006 boundary ß

Recommended approach:

1. Use the historical DAGI municipality source
2. Filter for Randers / code `0730`
3. Filter to a validity date in 2006, ideally `2006-12-31`
4. Export the resulting polygon
5. Manually verify it is the **pre-2007** Randers shape

## Licensing / attribution

DAGI data is part of Danish public geodata and should be attributed to **Klimadatastyrelsen / Dataforsyningen** under the current geodata terms.

## Risks / open questions

- Exact historical layer/service details should be confirmed before implementation
- Historical WFS/file-download details may require authenticated access
- Need to verify the exact temporal fields and layer name in the chosen service

## Recommendation for this project

Use the historical DAGI municipality dataset as the **source of truth** for the playable area boundary.

Do a one-off extraction for 2006 and commit only the processed derived geometry needed by the project.
