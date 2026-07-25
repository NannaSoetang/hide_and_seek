import L from 'leaflet'

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

export class LabelManager {
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
