import './style.css'
import L from 'leaflet'
import QRCode from 'qrcode'
import { createBaseMap, fitBoundsWithPadding, loadJson } from './shared.js'
import { cleanedStationName, filterTransportData, loadTransportData } from './transport.js'

const WEBSITE_URL_FALLBACK = 'https://nannasoetang.github.io/hide_and_seek/'

const METRO_LINE_COLORS = {
  M1: '#00a650',
  M2: '#f5c400',
  M3: '#e03b3b',
  M4: '#0072bc',
}

const METRO_LINE_PATTERNS = {
  M1: null,
  M2: '12 8',
  M3: '5 7',
  M4: '20 8 4 8',
}

const S_TOG_LINE_COLORS = {
  A: '#1f4e9e',
  B: '#2f9e44',
  C: '#f28e2b',
  F: '#f2a900',
}

const S_TOG_LINE_PATTERNS = {
  A: null,
  B: '12 8',
  C: '4 8',
  F: '18 6 4 6',
}

const ADMIN_STYLES = {
  kommuner: {
    color: '#2f4f79',
    weight: 1.9,
    opacity: 0.9,
    dashArray: '10 5',
    fillOpacity: 0,
  },
  postomraader: {
    color: '#2f7d9c',
    weight: 1.1,
    opacity: 0.54,
    dashArray: '4 8',
    fillOpacity: 0,
  },
  opstillingskredse: {
    color: '#3f7b4f',
    weight: 1.2,
    opacity: 0.58,
    dashArray: '8 6',
    fillOpacity: 0,
  },
  sogne: {
    color: '#8f5b7f',
    weight: 0.8,
    opacity: 0.32,
    dashArray: '2 8',
    fillOpacity: 0,
  },
}

function normalizeStationName(name) {
  return String(name || '')
    .toLowerCase()
    .replace(/\(.*?\)/g, '')
    .replace(/\bst\.?\b/g, '')
    .replace(/station/g, '')
    .replace(/[^\p{L}\p{N}]+/gu, ' ')
    .trim()
}

function addNorthArrow(map) {
  const NorthArrowControl = L.Control.extend({
    options: { position: 'topright' },
    onAdd() {
      const container = L.DomUtil.create('div', 'leaflet-control north-arrow-control')
      container.innerHTML = '<span class="north-arrow-label">N</span><span class="north-arrow-mark">▲</span>'
      return container
    },
  })
  map.addControl(new NorthArrowControl())
}

function addNamedBoundaryLayer(map, geojson, style) {
  return L.geoJSON(geojson, {
    interactive: false,
    style,
  }).addTo(map)
}

function addAreaLabels(map, geojson, field, className, options = {}) {
  const minZoom = options.minZoom ?? 11
  const dedupe = options.dedupe ?? false
  const shown = new Set()
  const markers = []

  for (const feature of geojson.features || []) {
    const raw = feature?.properties?.[field]
    if (!raw) continue
    const label = String(raw).trim()
    if (!label) continue
    const dedupeKey = label.toLowerCase()
    if (dedupe && shown.has(dedupeKey)) continue
    if (dedupe) shown.add(dedupeKey)

    const center = L.geoJSON(feature).getBounds().getCenter()
    const marker = L.marker(center, {
      interactive: false,
      icon: L.divIcon({
        className: `admin-label ${className}`,
        html: `<span>${label}</span>`,
      }),
    })
    markers.push(marker)
  }

  const labelLayer = L.layerGroup(markers).addTo(map)
  const toggle = () => {
    const shouldShow = map.getZoom() >= minZoom
    if (shouldShow && !map.hasLayer(labelLayer)) map.addLayer(labelLayer)
    if (!shouldShow && map.hasLayer(labelLayer)) map.removeLayer(labelLayer)
  }
  map.on('zoomend', toggle)
  toggle()
}

function addTransitLines(map, metroLines, sTogLines) {
  L.geoJSON(metroLines, {
    interactive: false,
    style: (feature) => ({
      color: METRO_LINE_COLORS[feature.properties?.line] || '#444',
      weight: 4.8,
      opacity: 0.92,
      dashArray: METRO_LINE_PATTERNS[feature.properties?.line] || null,
      lineCap: 'round',
      lineJoin: 'round',
    }),
  }).addTo(map)

  L.geoJSON(sTogLines, {
    interactive: false,
    style: {
      color: '#ffffff',
      weight: 9,
      opacity: 0.94,
      lineCap: 'round',
      lineJoin: 'round',
    },
  }).addTo(map)

  L.geoJSON(sTogLines, {
    interactive: false,
    style: (feature) => ({
      color: S_TOG_LINE_COLORS[feature.properties?.line] || '#333',
      weight: 6,
      opacity: 0.95,
      dashArray: S_TOG_LINE_PATTERNS[feature.properties?.line] || null,
      lineCap: 'round',
      lineJoin: 'round',
    }),
  }).addTo(map)
}

function buildStationIndex(metroStations, sTogStations) {
  const index = new Map()

  const include = (feature, network) => {
    const name = cleanedStationName(feature?.properties?.name)
    if (!name) return
    const normalized = normalizeStationName(name)
    if (!normalized) return

    const [lng, lat] = feature.geometry?.coordinates || []
    if (!Number.isFinite(lat) || !Number.isFinite(lng)) return

    if (!index.has(normalized)) {
      index.set(normalized, {
        name,
        lat,
        lng,
        networks: new Set(),
      })
    }
    index.get(normalized).networks.add(network)
  }

  for (const feature of metroStations.features || []) include(feature, 'metro')
  for (const feature of sTogStations.features || []) include(feature, 's-tog')
  return index
}

function addAllowedStations(map, metroStations, sTogStations) {
  const stationIndex = buildStationIndex(metroStations, sTogStations)
  for (const station of stationIndex.values()) {
    const latlng = [station.lat, station.lng]
    const isTransfer = station.networks.size > 1
    if (isTransfer) {
      L.circleMarker(latlng, {
        radius: 6,
        color: '#12243b',
        weight: 1.8,
        fillColor: '#ffffff',
        fillOpacity: 1,
        interactive: false,
      }).addTo(map)
      L.circleMarker(latlng, {
        radius: 2.4,
        color: '#12243b',
        weight: 0,
        fillColor: '#12243b',
        fillOpacity: 1,
        interactive: false,
      }).addTo(map)
      continue
    }

    L.circleMarker(latlng, {
      radius: 2.8,
      color: '#12243b',
      weight: 0,
      fillColor: '#12243b',
      fillOpacity: 1,
      interactive: false,
    }).addTo(map)
  }
}

function resolveWebsiteUrl() {
  if (window.location.hostname === '127.0.0.1' || window.location.hostname === 'localhost') {
    return WEBSITE_URL_FALLBACK
  }
  const baseUrl = import.meta.env.BASE_URL || '/'
  return new URL(baseUrl, window.location.origin).href
}

async function renderQrCode() {
  const qrElement = document.querySelector('#print-qr')
  const captionElement = document.querySelector('#print-qr-caption')
  if (!qrElement || !(qrElement instanceof HTMLImageElement)) return

  const websiteUrl = resolveWebsiteUrl()
  const qrDataUrl = await QRCode.toDataURL(websiteUrl, {
    width: 164,
    margin: 1,
    color: {
      dark: '#12243b',
      light: '#0000',
    },
  })
  qrElement.src = qrDataUrl
  if (captionElement) captionElement.textContent = websiteUrl
}

async function init() {
  const map = createBaseMap('print-map', {
    zoomControl: false,
    zoomSnap: 0.25,
    zoomDelta: 0.25,
    tileUrl: 'https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png',
    attribution: '&copy; OpenStreetMap-bidragsydere &copy; CARTO',
    subdomains: 'abcd',
    maxZoom: 19,
  })

  const transport = await loadTransportData()
  const metro = filterTransportData(transport, 'metro')
  const stog = filterTransportData(transport, 's-tog')

  const [
    boundary,
    municipalities,
    postAreas,
    constituencies,
    parishes,
  ] = await Promise.all([
    loadJson('/data/boundary.geojson'),
    loadJson('/data/municipalities.geojson'),
    loadJson('/data/postnumre.geojson'),
    loadJson('/data/opstillingskredse.geojson'),
    loadJson('/data/sogne.geojson'),
  ])

  const boundaryLayer = L.geoJSON(boundary, {
    style: {
      color: '#173459',
      weight: 2,
      opacity: 0.75,
      fillOpacity: 0,
    },
    interactive: false,
  }).addTo(map)

  addNamedBoundaryLayer(map, municipalities, ADMIN_STYLES.kommuner)
  addNamedBoundaryLayer(map, postAreas, ADMIN_STYLES.postomraader)
  addNamedBoundaryLayer(map, constituencies, ADMIN_STYLES.opstillingskredse)
  addNamedBoundaryLayer(map, parishes, ADMIN_STYLES.sogne)

  addTransitLines(map, metro.lines, stog.lines)
  addAllowedStations(map, metro.stations, stog.stations)

  addAreaLabels(map, municipalities, 'name', 'admin-label--kommuner', {
    minZoom: 9.2,
    dedupe: true,
  })
  addAreaLabels(map, postAreas, 'postnummernavn', 'admin-label--postomraader', {
    minZoom: 11.1,
    dedupe: true,
  })

  fitBoundsWithPadding(map, boundaryLayer, {
    paddingTopLeft: [10, 10],
    paddingBottomRight: [10, 10],
    maxZoom: 12,
  })

  L.control.scale({
    imperial: false,
    position: 'bottomleft',
  }).addTo(map)

  addNorthArrow(map)
  map.attributionControl.setPrefix('')
  await renderQrCode()
  document.body.dataset.printReady = 'true'
}

init().catch((error) => {
  console.error('Kunne ikke bygge printark.', error)
})
