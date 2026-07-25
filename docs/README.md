# Documentation Index

This folder contains short source notes for the Copenhagen map, preprocessing pipeline, and external data sources.

## Primary references

- `datasets/rejseplanen-gtfs.md`: GTFS source notes
- `datasets/dagi-sogne.md`: parish dataset notes
- `datasets/dagi-postnumre.md`: postal area dataset notes
- `datasets/dagi-opstillingskredse.md`: constituency dataset notes
- `datasets/dawa-addresses.md`: address lookup service notes
- `datasets/danish-basemap.md`: basemap provider notes

The repository README is the source of truth for setup, development, preprocessing, testing, and deployment. These files document source-specific context and licensing assumptions only.

## Maintenance guideline

When a source changes, update the relevant note in `docs/datasets/` and keep the pipeline and deployment sections in the README in sync with the implementation.
