# Randers Hide and Seek docs

<!-- TODO: Docs reference Randers. Update these notes or add a configuration
  section for alternate regions such as Storkøbenhavn. -->

Small research notes for the datasets and services currently in scope for the Randers Jet Lag: Hide and Seek helper tools.

## Dataset notes

- [Rejseplanen GTFS](./datasets/rejseplanen-gtfs.md)
- [DAGI historical kommune boundary](./datasets/dagi-historical-kommune.md)
- [DAGI sogne](./datasets/dagi-sogne.md)
- [DAGI postnumre](./datasets/dagi-postnumre.md)
- [DAGI opstillingskredse](./datasets/dagi-opstillingskredse.md)
- [Midttrafik fare zones](./datasets/midttrafik-fare-zones.md)
- [DAWA address search](./datasets/dawa-addresses.md)
- [Official Danish basemap options](./datasets/danish-basemap.md)

## Notes

- These files are planning/research notes, not implementation docs.
- Current project direction is to use one-off preprocessing and ship derived static data to the web app.
- Tooling preference locked in by user:
  - Python via `uv`
  - JavaScript via `npm`
