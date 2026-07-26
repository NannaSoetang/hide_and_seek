import './style.css'
import L from 'leaflet'
import { addBoundary, createBaseMap, loadBoundary, loadJson } from './shared.js'
import { AdministrativeLayer } from './AdministrativeLayer.js'
import { addTransportLayers, filterTransportData, fitTransportLayers, loadTransportData } from './transport.js'

const ADMIN_BOUNDARY_STYLES = {
  kommuner: {
    color: '#7b1fa2',
    weight: 4.0,
    opacity: 0.92,
    fillColor: '#8e24aa',
    fillOpacity: 0.18,
  },
  postomraader: {
    color: '#00838f',
    weight: 3.5,
    opacity: 0.88,
    fillColor: '#0097a7',
    fillOpacity: 0.18,
  },
  opstillingskredse: {
    color: '#c2185b',
    weight: 3.2,
    opacity: 0.88,
    fillColor: '#d81b60',
    fillOpacity: 0.18,
  },
  sogne: {
    color: '#6d4c41',
    weight: 2.8,
    opacity: 0.82,
    fillColor: '#795548',
    fillOpacity: 0.18,
  },
}

const SKIP_CONTEXT_CLICK_FLAG = '__skipNextContextClick'

function addClearFilterControl(map, adminLayers) {
  const control = L.control({ position: 'topright' })

  control.onAdd = () => {
    const container = L.DomUtil.create('div', 'leaflet-bar map-clear-filter-control')
    const button = L.DomUtil.create('button', 'map-clear-filter-button', container)
    button.type = 'button'
    button.textContent = 'Ryd filter'
    button.setAttribute('aria-label', 'Ryd linje- og lagfiltrering')

    const updateState = () => {
      const hasLineFilter = Boolean(map.__selectedTransitLine)
      const hasOverlayFilter = adminLayers.some((layer) => map.hasLayer(layer.overlay))
      const hasAnyFilter = hasLineFilter || hasOverlayFilter
      button.disabled = !hasAnyFilter
      button.classList.toggle('is-disabled', !hasAnyFilter)
    }

    L.DomEvent.disableClickPropagation(container)
    L.DomEvent.disableScrollPropagation(container)
    L.DomEvent.on(button, 'click', (event) => {
      L.DomEvent.stopPropagation(event)
      const hasLineFilter = Boolean(map.__selectedTransitLine)
      const hasOverlayFilter = adminLayers.some((layer) => map.hasLayer(layer.overlay))
      if (!hasLineFilter && !hasOverlayFilter) return

      map.__selectedTransitLine = null
      map.fire('transit-line-selected')

      for (const layer of adminLayers) {
        if (map.hasLayer(layer.overlay)) {
          map.removeLayer(layer.overlay)
        }
      }

      map.closePopup()
    })

    map.on('transit-line-selected', updateState)
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
  if (context.postomraade) lines.push(`<p><strong>Postområde:</strong> ${escapeHtml(context.postomraade)}</p>`)
  if (context.opstillingskreds) lines.push(`<p><strong>Opstillingskreds:</strong> ${escapeHtml(context.opstillingskreds)}</p>`)
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

const ADMIN_LAYER_CONFIGS = [
  {
    id: 'kommuner',
    displayName: 'Kommuner',
    dataFile: '/data/municipalities.geojson',
    style: ADMIN_BOUNDARY_STYLES.kommuner,
    labelField: 'name',
    popupTitleField: 'name',
    popupFields: [],
    labelMinZoom: 13.8,
    dedupeLabels: false,
    minLabelSpacingPx: 64,
  },
  {
    id: 'opstillingskredse',
    displayName: 'Opstillingskredse',
    dataFile: '/data/opstillingskredse.geojson',
    style: ADMIN_BOUNDARY_STYLES.opstillingskredse,
    labelField: 'name',
    popupTitleField: 'name',
    popupFields: [
      { key: 'name', label: 'Navn' },
    ],
    labelMinZoom: 14.1,
    dedupeLabels: false,
    minLabelSpacingPx: 70,
  },
  {
    id: 'postomraader',
    displayName: 'Postområder',
    dataFile: '/data/postnumre.geojson',
    style: ADMIN_BOUNDARY_STYLES.postomraader,
    labelField: 'postnummernavn',
    popupTitleField: 'postnummernavn',
    popupFields: [
      { key: 'postnummernavn', label: 'Postområde' },
    ],
    labelMinZoom: 14.2,
    dedupeLabels: true,
    minLabelSpacingPx: 72,
  },
  {
    id: 'sogne',
    displayName: 'Sogne',
    dataFile: '/data/sogne.geojson',
    style: ADMIN_BOUNDARY_STYLES.sogne,
    labelField: 'name',
    popupTitleField: 'name',
    popupFields: [
      { key: 'name', label: 'Sogn' },
    ],
    labelMinZoom: 14.7,
    dedupeLabels: false,
    minLabelSpacingPx: 76,
  },
]

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
    onStationClick: (stationInfo) => {
      map[SKIP_CONTEXT_CLICK_FLAG] = true
      showContextPopup(map, adminLayers, stationInfo.latlng, stationInfo)
    },
  })
  const sTogLayers = addTransportLayers(map, sTogData, 's-tog', {
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
    map.fitBounds(bounds.pad(0.08))
  } else {
    fitTransportLayers(map, metroLayers)
  }
  window.__appDebug = { map, metroLayers, sTogLayers, adminLayers }
  document.body.dataset.appReady = 'true'
}

init().catch((error) => {
  console.error('Could not load map boundary.', error)
})
