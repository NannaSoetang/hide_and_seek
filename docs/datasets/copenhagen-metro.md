# Copenhagen Metro static data

The Metro layer is generated from the public Rejseplanen static GTFS feed:

- Source: <https://www.rejseplanen.info/labs/GTFS.zip>
- Generator: `scripts/build_metro_data.py`
- Runtime files: `web/public/data/metro-lines.geojson` and `web/public/data/metro-stations.geojson`

The generator selects only routes named M1, M2, M3, and M4, uses their GTFS `shapes.txt` geometry, and derives stations from `stop_times.txt` and `stops.txt`. The browser loads only the committed static GeoJSON files; it never requests the live GTFS URL.

The downloaded feed contains `attributions.txt`, but no complete license text was found in the archive. Rejseplanen/Datahub terms should be confirmed before redistributing the derived files outside this project. OpenStreetMap is used only as the Leaflet basemap and is attributed in the map.
