# Copenhagen transport static data

The transport layer is generated from the public Rejseplanen static GTFS feed:

- Source: <https://www.rejseplanen.info/labs/GTFS.zip>
- Generator: `scripts/build_data.py`
- Runtime files: `web/public/data/transport-lines.geojson` and `web/public/data/transport-stations.geojson`

The frontend filters the unified transport GeoJSON into Metro and S-tog views at runtime.

The generator selects Metro routes M1-M4 and S-tog routes A/B/C/F, writes a shared line/station model, and derives stations from `stop_times.txt` and `stops.txt`. The browser loads only the committed static GeoJSON files; it never requests the live GTFS URL.

The downloaded feed contains `attributions.txt`, but no complete license text was found in the archive. Rejseplanen/Datahub terms should be confirmed before redistributing the derived files outside this project. OpenStreetMap is used only as the Leaflet basemap and is attributed in the map.