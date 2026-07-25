# Rejseplanen GTFS

## Overview

Rejseplanen exposes a public static GTFS Schedule ZIP at `https://www.rejseplanen.info/labs/GTFS.zip`.

The feed appears to be a normal static GTFS Schedule archive and includes standard files such as `agency.txt`, `calendar.txt`, `calendar_dates.txt`, `routes.txt`, `stops.txt`, `stop_times.txt`, `trips.txt`, and `shapes.txt`.

## What we can use it for

- Determine which stops are eligible on a Saturday
- <!-- TODO: Update GTFS notes to cover Storkøbenhavn or make kommune filter configurable -->
- Determine which routes serve Randers-area stops
- Derive route geometry from `shape_id` + `shapes.txt`
- Build a one-off processed dataset so the web app does not need live transit calls

## Likely key files

- `stops.txt`: stop names and coordinates
- `stop_times.txt`: trip-stop timing and stop order
- `trips.txt`: route/service/shape linkage
- `calendar.txt`: normal weekly service pattern
- `calendar_dates.txt`: exceptions to the normal pattern
- `routes.txt`: route identifiers and metadata
- `shapes.txt`: route/trip geometry
- `agency.txt`: operator metadata

## Risks / open questions

- No obvious license text was found inside the ZIP itself
- Refresh cadence is not clearly documented in the inspected feed
- The feed is large, especially `stop_times.txt` and `shapes.txt`
- Route geometry is trip/shape-based, not a single clean line per route number

## Recommendation for this project

Use this as the **primary source** for stop eligibility and route geometry.

For the user’s rules, process the feed one-off and derive:

- stops inside the old Randers boundary
- stops with at least **2 bus stop events/hour on average** in the Saturday 09:00–18:00 window
- routes that have at least **2 usable consecutive in-zone eligible stops**

This is currently the strongest practical dataset for the transit side of the project.
