import L from 'leaflet'
import { pointInGeometry } from './LookupService.js'

function labelPoint(featureGeometry) {
  const temp = L.geoJSON({ type: 'Feature', properties: {}, geometry: featureGeometry })
  const bounds = temp.getBounds()
  return bounds.isValid() ? bounds.getCenter() : null
}

function featureScore(featureGeometry) {
  const temp = L.geoJSON({ type: 'Feature', properties: {}, geometry: featureGeometry })
  const bounds = temp.getBounds()
  if (!bounds.isValid()) return 0
  const width = Math.abs(bounds.getEast() - bounds.getWest())
  const height = Math.abs(bounds.getNorth() - bounds.getSouth())
  return width * height
}

class LabelManager {
  constructor(map, layerId, geojson, options) {
    this.map = map
    this.layerId = layerId
    this.geojson = geojson
    this.labelField = options.labelField
    this.labelMinZoom = options.labelMinZoom ?? 13
    this.dedupeLabels = options.dedupeLabels ?? false
    this.minLabelSpacingPx = options.minLabelSpacingPx ?? 56
    this.candidates = this.buildCandidates()
  }

  paneName() {
    return `adminLabelPane-${this.layerId}`
  }

  ensurePane() {
    if (!this.map.getPane(this.paneName())) {
      this.map.createPane(this.paneName())
      const pane = this.map.getPane(this.paneName())
      pane.style.zIndex = '440'
      pane.style.pointerEvents = 'none'
    }
  }

  selectLabelFeatures() {
    const features = this.geojson.features || []
    if (!this.dedupeLabels) return features

    const selectedByLabel = new Map()
    for (const feature of features) {
      const label = String(feature.properties?.[this.labelField] || '').trim()
      if (!label) continue
      const current = selectedByLabel.get(label)
      const score = featureScore(feature.geometry)
      if (!current || score > current.score) {
        selectedByLabel.set(label, { feature, score })
      }
    }
    return Array.from(selectedByLabel.values(), (entry) => entry.feature)
  }

  buildCandidates() {
    this.ensurePane()
    const labelFeatures = this.selectLabelFeatures()

    return labelFeatures
      .map((feature) => {
        const label = String(feature.properties?.[this.labelField] || '').trim()
        if (!label) return null
        const center = labelPoint(feature.geometry)
        if (!center) return null
        return { label, center }
      })
      .filter(Boolean)
  }

  buildLabelLayerForCurrentZoom() {
    const zoom = this.map.getZoom()
    const occupiedCells = new Set()
    const markers = []

    for (const candidate of this.candidates) {
      const projected = this.map.project(candidate.center, zoom)
      const cellX = Math.floor(projected.x / this.minLabelSpacingPx)
      const cellY = Math.floor(projected.y / this.minLabelSpacingPx)
      const key = `${cellX}:${cellY}`
      if (occupiedCells.has(key)) continue
      occupiedCells.add(key)

      markers.push(
        L.marker(candidate.center, {
          pane: this.paneName(),
          interactive: false,
          icon: L.divIcon({
            className: `admin-label admin-label--${this.layerId}`,
            html: `<span>${candidate.label}</span>`,
          }),
        }),
      )
    }

    return L.layerGroup(markers)
  }

  shouldShowLabels(isOverlayEnabled) {
    return isOverlayEnabled && this.map.getZoom() >= this.labelMinZoom
  }
}

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
    const value = properties?.[this.config.labelField]
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
