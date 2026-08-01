import L from 'leaflet'
import { loadJson } from './shared.js'
import { LINE_COLORS } from './theme.js'

const RENDER_CONFIG = {
  lineTooltipSuffix: '-linjen',
  lineWeight: 7,
  selectedLineWeight: 12,
  normalOpacity: 0.95,
  selectedOpacity: 0.12,
  stationRadius: 5,
  selectedStationRadius: 8.5,
  stationWeight: 1.5,
  selectedStationWeight: 3,
  includeCasing: true,
  lineCasingWeight: 11,
  selectedLineCasingOpacity: 0.64,
  fadedLineCasingOpacity: 0.005,
}



function createStationGroup(latlng, style) {
  const marker = L.circleMarker(latlng, style)

  return {
    marker,
    group: L.featureGroup([
      L.circleMarker(latlng, {
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

  const baseStationStyle = {
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

    lineLayer.eachLayer(layer => {

        const selected =
            selection?.network === network &&
            selection.line === layer.feature.properties.line

        layer.setStyle({

            weight:
                selected
                ? config.selectedLineWeight
                : config.lineWeight,

            opacity:
                !selection
                    ? config.normalOpacity
                    : selected
                        ? 1
                        : config.selectedOpacity,

        })

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

