import { loadJson } from './shared.js'
import { geometryBounds, pointInBounds, pointInGeometry } from './PolygonLookup.js'

const DATA_FILES = {
  municipality: '/data/municipalities.geojson',
  postalArea: '/data/postnumre.geojson',
  parish: '/data/sogne.geojson',
  constituency: '/data/opstillingskredse.geojson',
}

const EMPTY_RESULT = {
  municipality: null,
  postalArea: null,
  parish: null,
  constituency: null,
}

function indexFeatures(geojson, valueSelector) {
  return (geojson.features || [])
    .map((feature) => ({
      geometry: feature.geometry,
      bounds: geometryBounds(feature.geometry),
      value: valueSelector(feature.properties || {}),
    }))
    .filter((entry) => entry.geometry && entry.bounds)
}

export class AdministrativeLookup {
  constructor(index) {
    this.index = index
  }

  static async create() {
    const [municipalities, postAreas, parishes, constituencies] = await Promise.all([
      loadJson(DATA_FILES.municipality),
      loadJson(DATA_FILES.postalArea),
      loadJson(DATA_FILES.parish),
      loadJson(DATA_FILES.constituency),
    ])

    return new AdministrativeLookup({
      municipality: indexFeatures(municipalities, (props) => props.name || null),
      postalArea: indexFeatures(postAreas, (props) => props.postnummernavn || null),
      parish: indexFeatures(parishes, (props) => props.name || null),
      constituency: indexFeatures(constituencies, (props) => props.name || null),
    })
  }

  findInLayer(layerEntries, point) {
    for (const entry of layerEntries) {
      if (!pointInBounds(point, entry.bounds)) continue
      if (pointInGeometry(point, entry.geometry)) {
        return entry.value
      }
    }
    return null
  }

  lookup(lat, lon) {
    const point = [lon, lat]
    return {
      municipality: this.findInLayer(this.index.municipality, point),
      postalArea: this.findInLayer(this.index.postalArea, point),
      parish: this.findInLayer(this.index.parish, point),
      constituency: this.findInLayer(this.index.constituency, point),
    }
  }

  hasAny(result) {
    return Object.values(result).some((value) => value)
  }

  emptyResult() {
    return { ...EMPTY_RESULT }
  }
}
