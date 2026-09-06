import L from 'leaflet'
import { loadJson } from './shared.js'
import { TRANSIT_LINE_THEME, buildTransitLineStyle, getTransitLineColor } from '../config/theme.js'

const STATION_PANE = 'transitStationPane'
const TRANSIT_LINE_PANE = 'transitLinePane'

function ensureTransitPane(map) {
  if (map.getPane(TRANSIT_LINE_PANE)) return
  const pane = map.createPane(TRANSIT_LINE_PANE)
  pane.style.zIndex = '360'
}

function ensureStationPane(map) {
  if (map.getPane(STATION_PANE)) return
  const pane = map.createPane(STATION_PANE)
  pane.style.zIndex = '430'
}

function createStationGroup(latlng, style) {
  const marker = L.circleMarker(latlng, style)
  const group = L.featureGroup([
    L.circleMarker(latlng, {
      pane: STATION_PANE,
      radius: 16,
      opacity: 0,
      fillOpacity: 0,
      weight: 0,
    }),
    marker,
  ])
  group.__stationMarker = marker
  return group
}

function applyStationStyle(layer, style) {
  layer.__stationMarker.setStyle(style)
}

export function clearSelectedStation(map) {
  const selectedLayer = map.__selectedStationLayer
  if (!selectedLayer) return
  applyStationStyle(selectedLayer, selectedLayer.__defaultStyle)
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
      features: (data.lines.features || []).filter((feature) => feature.properties?.network === network && feature.geometry),
    },
    stations: {
      type: 'FeatureCollection',
      features: (data.stations.features || []).filter((feature) => (feature.properties?.networks || []).includes(network)),
    },
  }
}

export function addTransportLayers(map, data, network, options = {}) {
  ensureTransitPane(map)
  ensureStationPane(map)

  const baseStationStyle = {
    pane: STATION_PANE,
    color: TRANSIT_LINE_THEME.stationColor,
    fillColor: TRANSIT_LINE_THEME.stationFill,
    fillOpacity: 1,
  }

  const stationStyle = {
    ...baseStationStyle,
    radius: TRANSIT_LINE_THEME.stationRadius,
    weight: 1.5,
  }

  const selectedStationStyle = {
    ...baseStationStyle,
    radius: TRANSIT_LINE_THEME.selectedStationRadius,
    weight: 2.5,
    fillColor: TRANSIT_LINE_THEME.stationSelectionFill,
  }

  const lineCasingLayer = L.geoJSON(data.lines, {
    pane: TRANSIT_LINE_PANE,
    interactive: false,
    style: () => ({
      color: TRANSIT_LINE_THEME.lineCasingColor,
      weight: TRANSIT_LINE_THEME.casingWeight,
      opacity: 0.95,
      fill: false,
      lineCap: 'round',
      lineJoin: 'round',
    }),
  })

  const lineLayer = L.geoJSON(data.lines, {
    pane: TRANSIT_LINE_PANE,
    bubblingMouseEvents: false,
    className: 'transit-line',
    style: (feature) => buildTransitLineStyle(feature),
    onEachFeature: (feature, layer) => {
      const line = feature.properties?.line
      layer.bindTooltip(`${line || ''} line`, { sticky: true, direction: 'center' })
      layer.on('click', () => {
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

  const updateLineStyles = () => {
    const selection = map.__selectedTransitLine
    const hasSelection = Boolean(selection)
    const isSelected = (featureLine) => selection?.network === network && selection.line === featureLine

    lineCasingLayer.eachLayer((layer) => {
      const lineName = layer.feature?.properties?.line
      const selected = isSelected(lineName)
      layer.setStyle({
        color: selected ? getTransitLineColor(layer.feature) : TRANSIT_LINE_THEME.lineCasingColor,
        weight: selected ? TRANSIT_LINE_THEME.casingWeight + 5 : TRANSIT_LINE_THEME.casingWeight,
        opacity: TRANSIT_LINE_THEME.mutedOpacity,
      })
      if (selected) layer.bringToFront()
    })

    lineLayer.eachLayer((layer) => {
      const lineName = layer.feature?.properties?.line
      const selected = isSelected(lineName)
      layer.setStyle(buildTransitLineStyle(layer.feature, { selected, hasSelection }))
      if (selected) layer.bringToFront()
    })
  }
  map.on('transit-line-selected', updateLineStyles)

  const stationLayer = L.geoJSON(data.stations, {
    pane: STATION_PANE,
    pointToLayer: (feature, latlng) => {
      return createStationGroup(latlng, stationStyle)
    },
    onEachFeature: (feature, layer) => {
      const name = feature.properties.name
      const lines = (feature.properties?.lines || []).map((line) => String(line))
      layer.__defaultStyle = stationStyle
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
        const stationLatLng = layer.__stationMarker.getLatLng()
        options.onStationClick?.({
          latlng: stationLatLng,
          stationName: name,
          lines: lines.join(', '),
          network,
        })
      })
    },
  })

  const group = L.layerGroup([lineCasingLayer, lineLayer, stationLayer]).addTo(map)
  return { group, lineLayer, stationLayer, lineCasingLayer }
}


