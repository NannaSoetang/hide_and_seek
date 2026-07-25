# DAGI postnumre

## Overview

`Postnummerinddeling` is the official DAGI polygon dataset for Danish postal areas.

It is the correct official source if the web map should optionally show **postnummer** areas.

## Relevant fields / data model

Important fields include:

- `postnummer`
- `navn`
- `erGadepostnummer`
- polygon geometry
- temporal and provenance metadata

## How we would use it in the web app

- draw postal code boundaries as an optional layer
- determine which postal area a point/address falls inside
- show postal code/name in the result panel if desired later

## Licensing / attribution

Official DAGI geodata is available under **CC BY 4.0** with attribution to **Klimadatastyrelsen**.

## Risks / open questions

- Datafordeler access patterns may require authenticated download/preprocessing
- Postal boundaries are operational areas, not guaranteed to align with municipality/parish borders
- `erGadepostnummer` creates edge cases and should still be preserved in the data model

## Recommendation for this project

Use `Postnummerinddeling` for the optional postal-code layer, but preprocess it one-off and only ship the simplified derived geometry needed by the app.
