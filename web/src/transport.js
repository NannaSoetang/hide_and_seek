import L from 'leaflet'
import { loadJson } from './shared.js'
import { TRANSIT_LINE_THEME, TRANSIT_NETWORKS, buildTransitLineStyle, getTransitLineColor } from './theme.js'

const RENDER_CONFIG = {
  lineTooltipSuffix: ' line',
  includeCasing: true,
}

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

  return {
    marker,
    group: L.featureGroup([
      L.circleMarker(latlng, {
        pane: STATION_PANE,
        radius: 16,
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
    radius: TRANSIT_LINE_THEME.stationRadius,
    color: TRANSIT_LINE_THEME.stationColor,
    weight: 1.5,
    fillColor: TRANSIT_LINE_THEME.stationFill,
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
      features: (data.lines.features || []).filter((feature) => feature.properties?.network === network && feature.geometry),
    },
    stations: {
      type: 'FeatureCollection',
      features: (data.stations.features || []).filter((feature) => (feature.properties?.networks || []).includes(network)),
    },
  }
}

function stationNetworkIndex(map, network, stations) {
  map.__stationIndex = map.__stationIndex || Object.fromEntries(TRANSIT_NETWORKS.map((item) => [item, []]))
  map.__stationIndex[network] = stations.features.map((feature) => feature.properties?.name || '')
}

export function addTransportLayers(map, data, network, options = {}) {
  stationNetworkIndex(map, network, data.stations)
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

  const lineLayers = []
  let lineCasingLayer = null
  if (RENDER_CONFIG.includeCasing) {
    lineCasingLayer = L.geoJSON(data.lines, {
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
    lineLayers.push(lineCasingLayer)
  }

  const lineLayer = L.geoJSON(data.lines, {
    pane: TRANSIT_LINE_PANE,
    bubblingMouseEvents: false,
    className: 'transit-line',
    style: (feature) => buildTransitLineStyle(feature),
    onEachFeature: (feature, layer) => {
      const line = feature.properties?.line
      layer.bindTooltip(`${line || ''}${RENDER_CONFIG.lineTooltipSuffix}`, { sticky: true, direction: 'center' })
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
    const hasSelection = Boolean(selection)
    const isSelected = (featureLine) => selection?.network === network && selection.line === featureLine

    lineCasingLayer?.eachLayer((layer) => {
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
      const station = createStationGroup(latlng, stationStyle)
      return station.group
    },
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

