import L from 'leaflet'
import { LabelManager } from './LabelManager.js'
import { pointInGeometry } from './PolygonLookup.js'

export class AdministrativeLayer {
  constructor(map, config, geojson) {
    this.map = map
    this.config = config
    this.geojson = geojson

    this.boundaryPaneName = `adminBoundaryPane-${config.id}`
    if (!this.map.getPane(this.boundaryPaneName)) {
      this.map.createPane(this.boundaryPaneName)
      const pane = this.map.getPane(this.boundaryPaneName)
      pane.style.zIndex = '360'
      pane.style.pointerEvents = 'none'
    }

    this.boundaryLayer = L.geoJSON(geojson, {
      pane: this.boundaryPaneName,
      interactive: false,
      style: config.style,
    })

    this.labelManager = new LabelManager(map, config.id, geojson, {
      labelField: config.labelField,
      labelMinZoom: config.labelMinZoom,
      dedupeLabels: config.dedupeLabels,
      minLabelSpacingPx: config.minLabelSpacingPx,
    })

    this.overlay = L.layerGroup([this.boundaryLayer])
    this.activeLabelLayer = null
    this.map.on('overlayadd overlayremove zoomend', () => this.updateLabelVisibility())
    this.updateLabelVisibility()
  }

  getPropertiesAtLatLng(latlng) {
    const point = [latlng.lng, latlng.lat]
    for (const feature of this.geojson.features || []) {
      if (pointInGeometry(point, feature.geometry)) {
        return feature.properties || null
      }
    }
    return null
  }

  getSummaryAtLatLng(latlng) {
    const properties = this.getPropertiesAtLatLng(latlng)
    if (!properties) return null
    const value = properties?.[this.config.popupTitleField]
    if (value === null || value === undefined || value === '') return null
    return String(value)
  }

  updateLabelVisibility() {
    const enabled = this.map.hasLayer(this.overlay)
    const show = this.labelManager.shouldShowLabels(enabled)
    const activeLayer = this.activeLabelLayer
    const canCheckActiveLayer = !!(activeLayer && typeof activeLayer === 'object')

    if (!show) {
      if (canCheckActiveLayer && this.overlay.hasLayer(activeLayer)) {
        this.overlay.removeLayer(activeLayer)
      }
      this.activeLabelLayer = null
      return
    }

    const nextLabelLayer = this.labelManager.buildLabelLayerForCurrentZoom()
    if (canCheckActiveLayer && this.overlay.hasLayer(activeLayer)) {
      this.overlay.removeLayer(activeLayer)
    }
    this.activeLabelLayer = nextLabelLayer
    this.overlay.addLayer(this.activeLabelLayer)
  }
}
