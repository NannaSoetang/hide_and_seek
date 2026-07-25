import './style.css'
import L from 'leaflet'
import { addBoundary, createBaseMap, loadBoundary } from './shared.js'
import { addMetroLayers, fitMetroLayers, loadMetroData } from './metro.js'
import { addSTogLayers, loadSTogData } from './stog.js'
import { ADMIN_BOUNDARY_STYLES } from './BoundaryStyle.js'
import { AdministrativeLayer } from './AdministrativeLayer.js'
import { loadAdministrativeLayers } from './LayerLoader.js'
import { buildContextPopup } from './PopupBuilder.js'

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
  const [boundary, metroData, sTogData, adminLayerData] = await Promise.all([
    loadBoundary(),
    loadMetroData(),
    loadSTogData(),
    loadAdministrativeLayers(ADMIN_LAYER_CONFIGS),
  ])
  const boundaryLayer = addBoundary(map, boundary)
  const adminLayers = ADMIN_LAYER_CONFIGS.map((config) => {
    return new AdministrativeLayer(map, config, adminLayerData[config.id])
  })

  const metroLayers = addMetroLayers(map, metroData, {
    onStationClick: (stationInfo) => {
      map.__skipNextContextClick = true
      showContextPopup(map, adminLayers, stationInfo.latlng, stationInfo)
    },
  })
  const sTogLayers = addSTogLayers(map, sTogData, {
    onStationClick: (stationInfo) => {
      map.__skipNextContextClick = true
      showContextPopup(map, adminLayers, stationInfo.latlng, stationInfo)
    },
  })

  map.on('click', (event) => {
    if (map.__skipNextContextClick) {
      map.__skipNextContextClick = false
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
  const bounds = boundaryLayer.getBounds()

  if (bounds.isValid()) {
    map.fitBounds(bounds.pad(0.08))
  } else {
    fitMetroLayers(map, metroLayers)
  }
  window.__appDebug = { map, metroLayers, sTogLayers, adminLayers }
  document.body.dataset.appReady = 'true'
}

init().catch((error) => {
  console.error('Could not load map boundary.', error)
})
