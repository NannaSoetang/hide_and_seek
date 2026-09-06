import 'leaflet/dist/leaflet.css'
import './map.css'
import './style.css'
import L from 'leaflet'
import { addBoundary, createBaseMap, loadBoundary, loadJson } from './shared.js'
import { AdministrativeLayer } from './AdministrativeLayer.js'
import { addTransportLayers, clearSelectedStation, filterTransportData, fitTransportLayers, loadTransportData } from './transport.js'
import { ADMIN_LAYERS, adminLayerStyle, getAdminLayerContextLabel, getAdminLayerLabel, TRANSIT_NETWORKS } from './theme.js'
import { APP_CONTENT } from './app-content.js'

const SKIP_CONTEXT_CLICK_FLAG = '__skipNextContextClick'
const UI = APP_CONTENT.mapPage

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
    button.textContent = UI.controls.clearFilter.text
    button.setAttribute('aria-label', UI.controls.clearFilter.ariaLabel)

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
  if (context.kommune) lines.push(`<p><strong>${getAdminLayerContextLabel('kommuner')}:</strong> ${escapeHtml(context.kommune)}</p>`)
  if (context.opstillingskreds) lines.push(`<p><strong>${getAdminLayerContextLabel('opstillingskredse')}:</strong> ${escapeHtml(context.opstillingskreds)}</p>`)
  if (context.postomraade) lines.push(`<p><strong>${getAdminLayerContextLabel('postomraader')}:</strong> ${escapeHtml(context.postomraade)}</p>`)
  if (context.sogn) lines.push(`<p><strong>${getAdminLayerContextLabel('sogne')}:</strong> ${escapeHtml(context.sogn)}</p>`)
  if (context.stationName) lines.push(`<p><strong>Station:</strong> ${escapeHtml(context.stationName)}</p>`)
  if (context.lines) lines.push(`<p><strong>Lines:</strong> ${escapeHtml(context.lines)}</p>`)

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

const ADMIN_LAYER_CONFIGS = ADMIN_LAYERS.map(layer => ({
  id: layer.id,
  displayName: layer.name,
  dataFile: `/data/${layer.file}`,
  style: adminLayerStyle(layer),
  labelField: layer.property,
  labelMinZoom: 14,
  dedupeLabels: layer.id === "postomraader",
  minLabelSpacingPx: 72,
}))

function showContextPopup(map, adminLayers, latlng, stationInfo = null) {
  if (!latlng) return
  const valuesById = Object.fromEntries(
    adminLayers.map((layer) => [layer.config.id, layer.getSummaryAtLatLng(latlng)]),
  )
  // When a stationInfo object is provided (station click), do not show administrative
  // summaries — only show station name and lines. For map/context clicks, include admin info.
  let context
  if (stationInfo) {
    context = {
      kommune: null,
      postomraade: null,
      opstillingskreds: null,
      sogn: null,
      stationName: stationInfo.stationName || null,
      lines: stationInfo.lines || null,
    }
  } else {
    context = {
      kommune: valuesById.kommuner,
      postomraade: valuesById.postomraader,
      opstillingskreds: valuesById.opstillingskredse,
      sogn: valuesById.sogne,
      stationName: stationInfo?.stationName || null,
      lines: stationInfo?.lines || null,
    }
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

function setMapState(mode, message = '') {
  const stateEl = document.querySelector('.map-state')
  if (!stateEl) return
  stateEl.textContent = message
  stateEl.classList.toggle('is-visible', mode !== 'hidden')
  stateEl.classList.toggle('is-loading', mode === 'loading')
  stateEl.classList.toggle('is-error', mode === 'error')
}

async function init() {
  setMapState('loading', 'Loading map…')
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

  const transportLayers = {}
  const englishAdminLayerNames = Object.fromEntries(
    ADMIN_LAYERS.map((layer) => [layer.id, getAdminLayerLabel(layer.id, 'en')]),
  )

  for (const network of TRANSIT_NETWORKS) {
    transportLayers[network] = addTransportLayers(
      map,
      filterTransportData(transportData, network),
      network,
      {
        onStationClick: (stationInfo) => {
          map[SKIP_CONTEXT_CLICK_FLAG] = true
          showContextPopup(map, adminLayers, stationInfo.latlng, stationInfo)
        },
      },
    )
  }

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

  const layerControl = L.control.layers(
    null,
    Object.fromEntries(adminLayers.map((layer) => [englishAdminLayerNames[layer.config.id] || layer.config.displayName, layer.overlay])),
    {
      collapsed: !window.matchMedia('(min-width: 700px)').matches,
      position: 'topright',
    },
  )
  layerControl.addTo(map)
  const updateLayerControlState = () => {
    const makeCollapsed = !window.matchMedia('(min-width: 700px)').matches
    if (makeCollapsed) {
      layerControl.collapse()
    } else {
      layerControl.expand()
    }
  }
  window.addEventListener('resize', updateLayerControlState)
  updateLayerControlState()
  addClearFilterControl(map, adminLayers)
  // Enable only the `kommuner` admin overlay by default so users see municipalities immediately
  const defaultAdminId = 'kommuner'
  for (const layer of adminLayers) {
    if (layer.config.id === defaultAdminId && !map.hasLayer(layer.overlay)) {
      map.addLayer(layer.overlay)
    }
  }
  const fallbackBounds = L.latLngBounds([
    [55.53, 12.30],
    [55.82, 12.73],
  ])
  const bounds = boundaryLayer.getBounds()

  if (bounds.isValid()) {
    map.__initialBounds = bounds.pad(0.12)
    map.fitBounds(map.__initialBounds)
  } else {
    map.__initialBounds = fallbackBounds
    map.fitBounds(fallbackBounds)
  }

  if (map.getZoom() > 12) {
    map.setZoom(12)
  }
  setMapState('hidden')
  window.__appDebug = { map, transportLayers, adminLayers }
  document.body.dataset.appReady = 'true'
}

init().catch((error) => {
  console.error('Could not load map boundary.', error)
  setMapState('error', 'Map unavailable. Please refresh the page and try again.')
  document.body.dataset.appReady = 'false'
})
