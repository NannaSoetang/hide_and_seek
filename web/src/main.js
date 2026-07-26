import './style.css'
import L from 'leaflet'
import { addBoundary, createBaseMap, loadBoundary, loadJson } from './shared.js'
import { AdministrativeLayer } from './AdministrativeLayer.js'
import { addTransportLayers, clearSelectedStation, filterTransportData, fitTransportLayers, loadTransportData } from './transport.js'
import { ADMIN_LAYERS, adminLayerStyle } from './theme.js'

const SKIP_CONTEXT_CLICK_FLAG = '__skipNextContextClick'

function hasActiveMapState(map, adminLayers) {
  const hasLineFilter = Boolean(map.__selectedTransitLine)
  const hasOverlayFilter = adminLayers.some((layer) => map.hasLayer(layer.overlay))
  const hasStationSelection = Boolean(map.__selectedStationLayer)
  return hasLineFilter || hasOverlayFilter || hasStationSelection
}

function hasClearableSelection(map) {
  return Boolean(map.__selectedTransitLine) || Boolean(map.__selectedStationLayer)
}

function clearTransientSelections(map) {
  if (!hasClearableSelection(map)) return false

  map.__selectedTransitLine = null
  map.fire('transit-line-selected')
  clearSelectedStation(map)

  map.closePopup()
  return true
}

function resetMapToOriginalState(map, adminLayers) {
  if (!hasActiveMapState(map, adminLayers)) return false

  map.__selectedTransitLine = null
  map.fire('transit-line-selected')
  clearSelectedStation(map)

  for (const layer of adminLayers) {
    if (map.hasLayer(layer.overlay)) {
      map.removeLayer(layer.overlay)
    }
  }

  map.closePopup()
  return true
}

function addClearFilterControl(map, adminLayers) {
  const control = L.control({ position: 'topright' })

  control.onAdd = () => {
    const container = L.DomUtil.create('div', 'leaflet-bar map-clear-filter-control')
    const button = L.DomUtil.create('button', 'map-clear-filter-button', container)
    button.type = 'button'
    button.textContent = 'Ryd filter'
    button.setAttribute('aria-label', 'Ryd linje- og lagfiltrering')

    const updateState = () => {
      const hasAnyFilter = hasActiveMapState(map, adminLayers)
      button.disabled = !hasAnyFilter
      button.classList.toggle('is-disabled', !hasAnyFilter)
    }

    L.DomEvent.disableClickPropagation(container)
    L.DomEvent.disableScrollPropagation(container)
    L.DomEvent.on(button, 'click', (event) => {
      L.DomEvent.stopPropagation(event)
      resetMapToOriginalState(map, adminLayers)
      updateState()
    })

    map.on('transit-line-selected', updateState)
    map.on('transit-station-selected', updateState)
    map.on('overlayadd overlayremove', updateState)
    updateState()
    return container
  }

  control.addTo(map)
}

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;')
}

function buildContextPopup(context) {
  const lines = []
  if (context.kommune) lines.push(`<p><strong>Kommune:</strong> ${escapeHtml(context.kommune)}</p>`)
  if (context.opstillingskreds) lines.push(`<p><strong>Opstillingskreds:</strong> ${escapeHtml(context.opstillingskreds)}</p>`)
  if (context.postomraade) lines.push(`<p><strong>Postområde:</strong> ${escapeHtml(context.postomraade)}</p>`)
  if (context.sogn) lines.push(`<p><strong>Sogn:</strong> ${escapeHtml(context.sogn)}</p>`)
  if (context.stationName) lines.push(`<p><strong>Station:</strong> ${escapeHtml(context.stationName)}</p>`)
  if (context.lines) lines.push(`<p><strong>Linjer:</strong> ${escapeHtml(context.lines)}</p>`)

  return [
    '<article class="admin-popup">',
    ...lines,
    '</article>',
  ].join('')
}

async function loadAdministrativeLayers(configs) {
  const entries = await Promise.all(
    configs.map(async (config) => {
      const data = await loadJson(config.dataFile)
      return [config.id, data]
    }),
  )
  return Object.fromEntries(entries)
}

const ADMIN_LAYER_CONFIGS = ADMIN_LAYERS.map((layer) => ({
  id: layer.id,
  displayName: layer.displayName,
  dataFile: `/data/${layer.dataFile}`,
  style: adminLayerStyle(layer),
  labelField: layer.labelField,
  popupTitleField: layer.popupTitleField,
  labelMinZoom: layer.labelMinZoom,
  dedupeLabels: layer.dedupeLabels,
  minLabelSpacingPx: layer.minLabelSpacingPx,
}))

function showContextPopup(map, adminLayers, latlng, stationInfo = null) {
  if (!latlng) return
  const valuesById = Object.fromEntries(
    adminLayers.map((layer) => [layer.config.id, layer.getSummaryAtLatLng(latlng)]),
  )
  const context = {
    kommune: valuesById.kommuner,
    postomraade: valuesById.postomraader,
    opstillingskreds: valuesById.opstillingskredse,
    sogn: valuesById.sogne,
    stationName: stationInfo?.stationName || null,
    lines: stationInfo?.lines || null,
  }

  const hasContent = Object.values(context).some((value) => value)
  if (!hasContent) return

  L.popup({
    autoPan: true,
    closeButton: true,
  })
    .setLatLng(latlng)
    .setContent(buildContextPopup(context))
    .openOn(map)
}

async function init() {
  const map = createBaseMap('map')
  const [boundary, transportData, adminLayerData] = await Promise.all([
    loadBoundary(),
    loadTransportData(),
    loadAdministrativeLayers(ADMIN_LAYER_CONFIGS),
  ])
  const boundaryLayer = addBoundary(map, boundary)
  const adminLayers = ADMIN_LAYER_CONFIGS.map((config) => {
    return new AdministrativeLayer(map, config, adminLayerData[config.id])
  })
  const metroData = filterTransportData(transportData, 'metro')
  const sTogData = filterTransportData(transportData, 's-tog')

  const metroLayers = addTransportLayers(map, metroData, 'metro', {
    onLineClick: () => {
      map[SKIP_CONTEXT_CLICK_FLAG] = true
    },
    onStationClick: (stationInfo) => {
      map[SKIP_CONTEXT_CLICK_FLAG] = true
      showContextPopup(map, adminLayers, stationInfo.latlng, stationInfo)
    },
  })
  const sTogLayers = addTransportLayers(map, sTogData, 's-tog', {
    onLineClick: () => {
      map[SKIP_CONTEXT_CLICK_FLAG] = true
    },
    onStationClick: (stationInfo) => {
      map[SKIP_CONTEXT_CLICK_FLAG] = true
      showContextPopup(map, adminLayers, stationInfo.latlng, stationInfo)
    },
  })

  map.on('click', (event) => {
    if (map[SKIP_CONTEXT_CLICK_FLAG]) {
      map[SKIP_CONTEXT_CLICK_FLAG] = false
      return
    }

    if (clearTransientSelections(map)) {
      return
    }

    showContextPopup(map, adminLayers, event.latlng)
  })

  L.control.layers(
    null,
    Object.fromEntries(adminLayers.map((layer) => [layer.config.displayName, layer.overlay])),
    {
      collapsed: true,
      position: 'topright',
    },
  ).addTo(map)
  addClearFilterControl(map, adminLayers)
  const bounds = boundaryLayer.getBounds()

  if (bounds.isValid()) {
    map.__initialBounds = bounds.pad(0.08)
    map.fitBounds(map.__initialBounds)
  } else {
    fitTransportLayers(map, metroLayers)
  }
  window.__appDebug = { map, metroLayers, sTogLayers, adminLayers }
  document.body.dataset.appReady = 'true'
}

init().catch((error) => {
  console.error('Could not load map boundary.', error)
})
