import L from 'leaflet'
import { loadJson } from './shared.js'

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

function cleanedStationName(name) {
  return String(name || '').replace(/\s*\(Metro\)\s*/gi, '').trim()
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

function createStationGroup(latlng, markerStyle) {
  const hitArea = L.circleMarker(latlng, {
    radius: 14,
    color: '#000',
    opacity: 0,
    fillColor: '#000',
    fillOpacity: 0,
    weight: 0,
  })
  const visibleMarker = L.circleMarker(latlng, markerStyle)
  const group = L.featureGroup([hitArea, visibleMarker])
  group.__visibleMarker = visibleMarker
  return group
}

function applyStationStyle(layer, style) {
  layer.__visibleMarker?.setStyle(style)
}

export async function loadMetroData() {
  const [lines, stations] = await Promise.all([
    loadJson('/data/metro-lines.geojson'),
    loadJson('/data/metro-stations.geojson'),
  ])
  return { lines, stations }
}

export function addMetroLayers(map, data, options = {}) {
  let selectedLine = null
  const sTogStationNames = new Set(
    (map.__stationIndex?.stog || []).map((name) => normalizeStationName(name)),
  )
  map.__stationIndex = map.__stationIndex || { metro: [], stog: [] }
  map.__stationIndex.metro = data.stations.features.map((feature) => feature.properties?.name || '')

  const stationStyle = {
    radius: 5,
    color: '#172033',
    weight: 1.5,
    fillColor: '#fff',
    fillOpacity: 1,
  }
  const markedStationStyle = {
    radius: 8.5,
    color: '#172033',
    weight: 3,
    fillColor: '#ffd54a',
    fillOpacity: 1,
  }
  const baseStyle = (feature) => ({
    color: METRO_LINE_COLORS[feature.properties?.line] || feature.properties?.color || '#333',
    weight: 5,
    opacity: 0.9,
    dashArray: METRO_LINE_PATTERNS[feature.properties?.line] || null,
    lineCap: 'round',
    lineJoin: 'round',
  })

  const lineLayer = L.geoJSON(data.lines, {
    style: baseStyle,
    onEachFeature: (feature, layer) => {
      const line = feature.properties?.line
      layer.bindTooltip(`${line || ''}-linjen`, { sticky: true })
      layer.on('click', () => {
        const isSameSelection = map.__selectedTransitLine?.network === 'metro'
          && map.__selectedTransitLine.line === line
        map.__selectedTransitLine = isSameSelection ? null : { network: 'metro', line }
        map.fire('transit-line-selected')
      })
    },
  })

  const updateLineStyles = () => {
    selectedLine = map.__selectedTransitLine?.network === 'metro'
      ? map.__selectedTransitLine.line
      : null
    lineLayer.eachLayer((candidate) => {
      const candidateLine = candidate.feature?.properties?.line
      const isSelected = selectedLine && candidateLine === selectedLine
      candidate.setStyle({
        weight: isSelected ? 9 : 5,
        opacity: selectedLine ? (isSelected ? 1 : 0.2) : 0.9,
      })
    })
    if (selectedLine) {
      lineLayer.eachLayer((candidate) => {
        if (candidate.feature?.properties?.line === selectedLine) candidate.bringToFront()
      })
    }
  }
  map.on('transit-line-selected', updateLineStyles)

  const stationLayer = L.geoJSON(data.stations, {
    pointToLayer: (_feature, latlng) => createStationGroup(latlng, stationStyle),
    onEachFeature: (feature, layer) => {
      const name = cleanedStationName(feature.properties?.name || 'Metrostation')
      const lines = (feature.properties?.lines || []).map((line) => String(line))
      const isTransfer = sTogStationNames.has(normalizeStationName(name))
      layer.on('click', () => {
        const previous = map.__selectedStationLayer
        if (previous && previous !== layer) {
          applyStationStyle(previous, stationStyle)
        }
        if (previous === layer) {
          applyStationStyle(layer, stationStyle)
          map.__selectedStationLayer = null
          return
        }
        applyStationStyle(layer, markedStationStyle)
        map.__selectedStationLayer = layer
        const stationLatLng = layer.getLayers?.()[0]?.getLatLng?.() || null
        options.onStationClick?.({
          latlng: stationLatLng,
          stationName: name,
          lines: lines.join(', '),
          network: 'metro',
          isTransfer,
        })
      })
    },
  })

  const group = L.layerGroup([lineLayer, stationLayer]).addTo(map)
  return { group, lineLayer, stationLayer }
}

export function fitMetroLayers(map, metroLayers) {
  const bounds = L.featureGroup([
    metroLayers.lineLayer,
    metroLayers.stationLayer,
  ]).getBounds()
  if (bounds.isValid()) map.fitBounds(bounds.pad(0.08))
}
