import L from 'leaflet'
import { loadJson } from './shared.js'

const S_LINE_COLORS = {
  A: '#1f4e9e',
  B: '#2f9e44',
  C: '#f28e2b',
  F: '#f2a900',
}

const S_LINE_PATTERNS = {
  A: null,
  B: '12 8',
  C: '4 8',
  F: '18 6 4 6',
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

export async function loadSTogData() {
  const [lines, stations] = await Promise.all([
    loadJson('/data/s-tog-lines.geojson'),
    loadJson('/data/s-tog-stations.geojson'),
  ])
  return { lines, stations }
}

export function addSTogLayers(map, data, options = {}) {
  let selectedLine = null
  const metroStationNames = new Set(
    (map.__stationIndex?.metro || []).map((name) => normalizeStationName(name)),
  )
  map.__stationIndex = map.__stationIndex || { metro: [], stog: [] }
  map.__stationIndex.stog = data.stations.features.map((feature) => feature.properties?.name || '')

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
  const lineCasingLayer = L.geoJSON(data.lines, {
    interactive: false,
    style: {
      color: '#ffffff',
      weight: 11,
      opacity: 0.95,
      lineCap: 'round',
      lineJoin: 'round',
    },
  })
  const lineLayer = L.geoJSON(data.lines, {
    style: (feature) => ({
      color: S_LINE_COLORS[feature.properties?.line] || '#333',
      weight: 7,
      opacity: 1,
      dashArray: S_LINE_PATTERNS[feature.properties?.line] || null,
      lineCap: 'round',
      lineJoin: 'round',
    }),
    onEachFeature: (feature, layer) => {
      const line = feature.properties?.line
      layer.bindTooltip(`${line || ''}-linjen`, { sticky: true })
      layer.on('click', () => {
        const isSameSelection = map.__selectedTransitLine?.network === 's-tog'
          && map.__selectedTransitLine.line === line
        map.__selectedTransitLine = isSameSelection ? null : { network: 's-tog', line }
        map.fire('transit-line-selected')
      })
    },
  })

  const updateLineStyles = () => {
    selectedLine = map.__selectedTransitLine?.network === 's-tog'
      ? map.__selectedTransitLine.line
      : null
    lineLayer.eachLayer((candidate) => {
      const isSelected = selectedLine && candidate.feature?.properties?.line === selectedLine
      candidate.setStyle({
          weight: isSelected ? 10 : 7,
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
      const name = cleanedStationName(feature.properties?.name || 'S-tog station')
      const lines = (feature.properties?.lines || []).map((line) => String(line))
      const isTransfer = metroStationNames.has(normalizeStationName(name))
      layer.on('click', () => {
        const previous = map.__selectedStationLayer
        if (previous && previous !== layer) applyStationStyle(previous, stationStyle)
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
          network: 's-tog',
          isTransfer,
        })
      })
    },
  })

  const group = L.layerGroup([lineCasingLayer, lineLayer, stationLayer]).addTo(map)
  return { group, lineCasingLayer, lineLayer, stationLayer }
}

