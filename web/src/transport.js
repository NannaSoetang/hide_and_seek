import L from 'leaflet'
import { loadJson } from './shared.js'
import { LINE_COLORS } from './theme.js'

const RENDER_CONFIG = {
  lineTooltipSuffix: '-linjen',
  lineWeight: 7,
  selectedLineWeight: 12,
  normalOpacity: 0.95,
  inactiveLineColor: '#c8d0dc',
  includeCasing: true,
  lineCasingWeight: 11,
}

const STATION_PANE = 'transitStationPane'

function ensureStationPane(map) {
  if (map.getPane(STATION_PANE)) return
  const pane = map.createPane(STATION_PANE)
  pane.style.zIndex = '430'
}

function createStationGroup(latlng, style) {
  const marker = L.circleMarker(latlng, style)

  return {
    marker,
    group: L.featureGroup([
      L.circleMarker(latlng, {
        pane: STATION_PANE,
        radius: 14,
        opacity: 0,
        fillOpacity: 0,
        weight: 0,
      }),
      marker,
    ]),
  }
}

function applyStationStyle(layer, style) {
  layer.marker?.setStyle(style)
}

export function clearSelectedStation(map) {
  const selectedLayer = map.__selectedStationLayer
  if (!selectedLayer) return
  applyStationStyle(selectedLayer, selectedLayer.__defaultStyle || {
    radius: 5,
    color: '#172033',
    weight: 1.5,
    fillColor: '#fff',
    fillOpacity: 1,
  })
  map.__selectedStationLayer = null
  map.fire('transit-station-selected', { stationName: null })
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
  stationNetworkIndex(map, network, data.stations)
  ensureStationPane(map)

  const baseStationStyle = {
      pane: STATION_PANE,
      color:"#172033",
      fillColor:"#fff",
      fillOpacity:1,
  }

  const stationStyle = {
      ...baseStationStyle,
      radius:5,
      weight:1.5,
  }

  const selectedStationStyle = {
      ...baseStationStyle,
      radius:8.5,
      weight:3,
      fillColor:"#ffd54a",
  }

  const lineLayers = []
  let lineCasingLayer = null
  if (RENDER_CONFIG.includeCasing) {
    lineCasingLayer = L.geoJSON(data.lines, {
      interactive: false,
      style: {
        color: '#ffffff',
        weight: RENDER_CONFIG.lineCasingWeight,
        opacity: 0.95,
        lineCap: 'round',
        lineJoin: 'round',
      },
    })
    lineLayers.push(lineCasingLayer)
  }

  const lineLayer = L.geoJSON(data.lines, {
    bubblingMouseEvents: false,
    className: 'transit-line',
    style: (feature) => ({
      color: LINE_COLORS[feature.properties.line],
      weight: RENDER_CONFIG.lineWeight,
      opacity: 1,
      lineCap: 'round',
      lineJoin: 'round',
    }),
    onEachFeature: (feature, layer) => {
      const line = feature.properties?.line
      layer.bindTooltip(`${line || ''}${RENDER_CONFIG.lineTooltipSuffix}`, { sticky: true })
      layer.on('click', () => {
          options.onLineClick?.({ network, line })
        if (map.__selectedStationLayer) {
          clearSelectedStation(map)
        }
        const isSameSelection = map.__selectedTransitLine?.network === network
          && map.__selectedTransitLine.line === line
        map.__selectedTransitLine = isSameSelection ? null : { network, line }
        map.fire('transit-line-selected')
      })
    },
  })
  lineLayers.push(lineLayer)

  const updateLineStyles = () => {
    const selection = map.__selectedTransitLine

    const isSelected = layer => selection?.network === network
      && selection.line === layer.feature.properties.line

    lineCasingLayer?.eachLayer(layer => {
      const selected = isSelected(layer)
      layer.setStyle({
        weight: selected
          ? RENDER_CONFIG.selectedLineWeight + 4
          : RENDER_CONFIG.lineCasingWeight,
        opacity: RENDER_CONFIG.normalOpacity,
      })
      if (selected) layer.bringToFront()
    })

    lineLayer.eachLayer(layer => {
      const selected = isSelected(layer)
      layer.setStyle({
        color: selection && !selected
          ? RENDER_CONFIG.inactiveLineColor
          : LINE_COLORS[layer.feature.properties.line],
        weight: selected
          ? RENDER_CONFIG.selectedLineWeight
          : RENDER_CONFIG.lineWeight,
        opacity: selected ? 1 : RENDER_CONFIG.normalOpacity,
      })
      if (selected) layer.bringToFront()
    })
  }
  map.on('transit-line-selected', updateLineStyles)

  const stationLayer = L.geoJSON(data.stations, {
    pointToLayer: (feature, latlng) => {
    const station = createStationGroup(latlng, stationStyle)
    return station.group},
    onEachFeature: (feature, layer) => {
      const name = feature.properties.name
      const lines = (feature.properties?.lines || []).map((line) => String(line))
      applyStationStyle(layer, stationStyle)
      layer.on('click', () => {
        if (map.__selectedTransitLine) {
          map.__selectedTransitLine = null
          map.fire('transit-line-selected')
        }
        const previous = map.__selectedStationLayer
        if (previous && previous !== layer) {
          applyStationStyle(previous, stationStyle)
        }
        if (previous === layer) {
          clearSelectedStation(map)
          return
        }
        applyStationStyle(layer, selectedStationStyle)
        map.__selectedStationLayer = layer
        map.fire('transit-station-selected', {
          stationName: name,
          lines: lines.join(', '),
          network,
        })
        const stationLatLng = layer.getLayers?.()[0]?.getLatLng?.() || null
        options.onStationClick?.({
          latlng: stationLatLng,
          stationName: name,
          lines: lines.join(', '),
          network,
        })
      })
    },
  })

  const group = L.layerGroup([...lineLayers, stationLayer]).addTo(map)
  return { group, lineLayer, stationLayer, lineCasingLayer }
}

export function fitTransportLayers(map, transportLayers) {
  const layers = Object.values(transportLayers).flatMap(({ lineLayer, stationLayer }) => [
    lineLayer,
    stationLayer,
  ])

  const bounds = L.featureGroup(layers).getBounds()

  if (bounds.isValid()) {
    map.fitBounds(bounds.pad(0.08))
  }
}

