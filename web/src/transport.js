import L from 'leaflet'
import { loadJson } from './shared.js'

const BASE_TRANSIT_CONFIG = {
  lineTooltipSuffix: '-linjen',
  lineWeight: 7,
  selectedLineWeight: 10,
  normalOpacity: 0.9,
  selectedOpacity: 0.2,
  stationRadius: 5,
  selectedStationRadius: 8.5,
  stationWeight: 1.5,
  selectedStationWeight: 3,
  includeCasing: true,
  lineCasingWeight: 11,
}

const NETWORK_CONFIG = {
  metro: {
    ...BASE_TRANSIT_CONFIG,
    label: 'Metro',
    stationFallback: 'Metrostation',
    counterpart: 's-tog',
  },
  's-tog': {
    ...BASE_TRANSIT_CONFIG,
    label: 'S-tog',
    stationFallback: 'S-tog station',
    counterpart: 'metro',
  },
}

const NETWORK_COLORS = {
  metro: {
    M1: '#00a650',
    M2: '#f5c400',
    M3: '#e03b3b',
    M4: '#0072bc',
  },
  's-tog': {
    A: '#1f4e9e',
    B: '#2f9e44',
    C: '#f28e2b',
    F: '#f2a900',
  },
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

export async function loadTransportData() {
  const [lines, stations] = await Promise.all([
    loadJson('/data/transport-lines.geojson'),
    loadJson('/data/transport-stations.geojson'),
  ])
  return { lines, stations }
}

export function filterTransportData(data, network) {
  return {
    lines: {
      type: 'FeatureCollection',
      features: (data.lines.features || []).filter((feature) => feature.properties?.network === network),
    },
    stations: {
      type: 'FeatureCollection',
      features: (data.stations.features || []).filter((feature) => (feature.properties?.networks || []).includes(network)),
    },
  }
}

function stationNetworkIndex(map, network, stations) {
  map.__stationIndex = map.__stationIndex || { metro: [], 's-tog': [] }
  map.__stationIndex[network] = stations.features.map((feature) => feature.properties?.name || '')
}

export function addTransportLayers(map, data, network, options = {}) {
  const config = NETWORK_CONFIG[network]
  if (!config) throw new Error(`Unknown transport network: ${network}`)

  let selectedLine = null
  const counterpartStationNames = new Set(
    (map.__stationIndex?.[config.counterpart] || []).map((name) => normalizeStationName(name)),
  )
  stationNetworkIndex(map, network, data.stations)

  const stationStyle = {
    radius: config.stationRadius,
    color: '#172033',
    weight: config.stationWeight,
    fillColor: '#fff',
    fillOpacity: 1,
  }
  const markedStationStyle = {
    radius: config.selectedStationRadius,
    color: '#172033',
    weight: config.selectedStationWeight,
    fillColor: '#ffd54a',
    fillOpacity: 1,
  }

  const lineLayers = []
  let lineCasingLayer = null
  if (config.includeCasing) {
    lineCasingLayer = L.geoJSON(data.lines, {
      interactive: false,
      style: {
        color: '#ffffff',
        weight: config.lineCasingWeight,
        opacity: 0.95,
        lineCap: 'round',
        lineJoin: 'round',
      },
    })
    lineLayers.push(lineCasingLayer)
  }

  const lineLayer = L.geoJSON(data.lines, {
    style: (feature) => ({
      color: NETWORK_COLORS[network][feature.properties?.line] || feature.properties?.color || '#333',
      weight: config.lineWeight,
      opacity: 1,
      lineCap: 'round',
      lineJoin: 'round',
    }),
    onEachFeature: (feature, layer) => {
      const line = feature.properties?.line
      layer.bindTooltip(`${line || ''}${config.lineTooltipSuffix}`, { sticky: true })
      layer.on('click', () => {
        const isSameSelection = map.__selectedTransitLine?.network === network
          && map.__selectedTransitLine.line === line
        map.__selectedTransitLine = isSameSelection ? null : { network, line }
        map.fire('transit-line-selected')
      })
    },
  })
  lineLayers.push(lineLayer)

  const updateLineStyles = () => {
    const selectedTransitLine = map.__selectedTransitLine
    selectedLine = selectedTransitLine?.network === network
      ? selectedTransitLine.line
      : null

    const styleForLine = (candidateLine) => {
      const isSelected = Boolean(
        selectedTransitLine
        && selectedTransitLine.network === network
        && candidateLine === selectedTransitLine.line,
      )
      return {
        isSelected,
        lineOpacity: selectedTransitLine ? (isSelected ? 1 : config.selectedOpacity) : config.normalOpacity,
      }
    }

    lineLayer.eachLayer((candidate) => {
      const candidateLine = candidate.feature?.properties?.line
      const { isSelected, lineOpacity } = styleForLine(candidateLine)
      candidate.setStyle({
        weight: isSelected ? config.selectedLineWeight : config.lineWeight,
        opacity: lineOpacity,
      })
    })

    lineCasingLayer?.eachLayer((candidate) => {
      const candidateLine = candidate.feature?.properties?.line
      const { isSelected, lineOpacity } = styleForLine(candidateLine)
      candidate.setStyle({
        opacity: isSelected ? 0.95 : lineOpacity,
      })
    })

    if (selectedLine) {
      lineLayer.eachLayer((candidate) => {
        if (candidate.feature?.properties?.line === selectedLine) candidate.bringToFront()
      })
      lineCasingLayer?.eachLayer((candidate) => {
        if (candidate.feature?.properties?.line === selectedLine) candidate.bringToFront()
      })
    }
  }
  map.on('transit-line-selected', updateLineStyles)

  const stationLayer = L.geoJSON(data.stations, {
    pointToLayer: (_feature, latlng) => createStationGroup(latlng, stationStyle),
    onEachFeature: (feature, layer) => {
      const name = cleanedStationName(feature.properties?.name || config.stationFallback)
      const lines = (feature.properties?.lines || []).map((line) => String(line))
      const isTransfer = counterpartStationNames.has(normalizeStationName(name))
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
          network,
          isTransfer,
        })
      })
    },
  })

  const group = L.layerGroup([...lineLayers, stationLayer]).addTo(map)
  return { group, lineLayer, stationLayer, lineCasingLayer }
}

export function fitTransportLayers(map, transportLayers) {
  const layers = [transportLayers.lineLayer, transportLayers.stationLayer].filter(Boolean)
  const bounds = L.featureGroup(layers).getBounds()
  if (bounds.isValid()) map.fitBounds(bounds.pad(0.08))
}

export { cleanedStationName, normalizeStationName }
