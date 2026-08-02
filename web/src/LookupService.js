import { loadJson } from './shared.js'

// --- Point in Geometry helpers ---

function pointInRing(point, ring) {
  let inside = false
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i, i += 1) {
    const xi = ring[i][0]
    const yi = ring[i][1]
    const xj = ring[j][0]
    const yj = ring[j][1]
    const intersects = ((yi > point[1]) !== (yj > point[1]))
      && (point[0] < ((xj - xi) * (point[1] - yi)) / ((yj - yi) || Number.EPSILON) + xi)
    if (intersects) inside = !inside
  }
  return inside
}

function pointInPolygon(point, coordinates) {
  if (!coordinates?.length) return false
  if (!pointInRing(point, coordinates[0])) return false
  for (let holeIndex = 1; holeIndex < coordinates.length; holeIndex += 1) {
    if (pointInRing(point, coordinates[holeIndex])) return false
  }
  return true
}

export function pointInGeometry(point, geometry) {
  if (!geometry) return false
  if (geometry.type === 'Polygon') {
    return pointInPolygon(point, geometry.coordinates)
  }
  if (geometry.type === 'MultiPolygon') {
    return geometry.coordinates.some((polygon) => pointInPolygon(point, polygon))
  }
  return false
}

function geometryBounds(geometry) {
  if (!geometry) return null
  const coords = []
  if (geometry.type === 'Polygon') {
    coords.push(...geometry.coordinates.flat())
  } else if (geometry.type === 'MultiPolygon') {
    coords.push(...geometry.coordinates.flat(2))
  } else {
    return null
  }
  if (!coords.length) return null
  const xs = coords.map((c) => c[0])
  const ys = coords.map((c) => c[1])
  return {
    minX: Math.min(...xs),
    minY: Math.min(...ys),
    maxX: Math.max(...xs),
    maxY: Math.max(...ys),
  }
}

function pointInBounds(point, bounds) {
  if (!bounds) return false
  return point[0] >= bounds.minX
    && point[0] <= bounds.maxX
    && point[1] >= bounds.minY
    && point[1] <= bounds.maxY
}

// --- Administrative Area Lookup ---

const DATA_FILES = {
  municipality: '/data/municipalities.geojson',
  postalArea: '/data/postnumre.geojson',
  parish: '/data/sogne.geojson',
  constituency: '/data/opstillingskredse.geojson',
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
}

// --- Device Geolocation Lookup ---

function geolocationErrorMessage(error) {
  if (!error) return 'Kunne ikke hente din placering.'
  if (error.code === 1) {
    return 'Placering er blokeret. Tillad lokalitet i Safari-indstillinger og prøv igen.'
  }
  if (error.code === 2) {
    return 'Placering er midlertidigt utilgængelig. Prøv igen om et øjeblik.'
  }
  if (error.code === 3) {
    return 'Placering tog for lang tid. Prøv igen med bedre signal.'
  }
  return 'Kunne ikke hente din placering.'
}

export function getCurrentPosition() {
  return new Promise((resolve, reject) => {
    if (!('geolocation' in navigator)) {
      reject(new Error('Din browser understøtter ikke geolokation.'))
      return
    }

    navigator.geolocation.getCurrentPosition(
      (position) => resolve(position),
      (error) => reject(new Error(geolocationErrorMessage(error))),
      {
        enableHighAccuracy: true,
        timeout: 12000,
        maximumAge: 3000,
      },
    )
  })
}

// --- Dataforsyningen Address Search & Resolution ---

const AUTOCOMPLETE_ENDPOINTS = [
  'https://api.dataforsyningen.dk/adresser/autocomplete',
  'https://api.dataforsyningen.dk/autocomplete',
]

const ADDRESS_DETAIL_ENDPOINTS = [
  'https://api.dataforsyningen.dk/adresser',
]

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options)
  if (!response.ok) throw new Error(`HTTP ${response.status}`)
  return response.json()
}

function buildUrl(base, params) {
  const url = new URL(base)
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      url.searchParams.set(key, String(value))
    }
  })
  return url.toString()
}

function toSuggestion(item) {
  if (typeof item === 'string') {
    return { id: null, text: item, lon: null, lat: null }
  }
  const text = item.tekst
    || item.adressebetegnelse
    || item.forslagstekst
    || item.label
    || item.værdi
    || ''

  const id = item.id || item.adresse?.id || null
  const lon = item.x ?? item.adgangsadresse?.adgangspunkt?.koordinater?.[0] ?? null
  const lat = item.y ?? item.adgangsadresse?.adgangspunkt?.koordinater?.[1] ?? null

  return { id, text, lon, lat }
}

export async function searchAddresses(query, { signal } = {}) {
  if (!query || query.trim().length < 3) return []

  let receivedResponse = false
  for (const endpoint of AUTOCOMPLETE_ENDPOINTS) {
    try {
      const payload = await fetchJson(
        buildUrl(endpoint, { q: query, fuzzy: '' }),
        { signal },
      )
      receivedResponse = true
      const candidates = Array.isArray(payload)
        ? payload
        : (payload?.resultater || payload?.hits || [])
      const suggestions = candidates.map(toSuggestion).filter((item) => item.text)
      if (suggestions.length) return suggestions.slice(0, 5)
    } catch (error) {
      if (error.name === 'AbortError') throw error
      // try next endpoint
    }
  }
  if (!receivedResponse) {
    throw new Error('Adressesøgning er midlertidigt utilgængelig. Prøv igen senere.')
  }
  return []
}

export async function resolveAddressToCoordinates(suggestion) {
  if (suggestion.lat !== null && suggestion.lon !== null) {
    return { lat: Number(suggestion.lat), lon: Number(suggestion.lon), label: suggestion.text }
  }
  if (!suggestion.id) {
    throw new Error('Kunne ikke finde koordinater for den valgte adresse.')
  }

  for (const endpoint of ADDRESS_DETAIL_ENDPOINTS) {
    try {
      const payload = await fetchJson(buildUrl(endpoint, { id: suggestion.id }))
      const item = Array.isArray(payload) ? payload[0] : payload
      const coords = item?.adgangsadresse?.adgangspunkt?.koordinater
      if (Array.isArray(coords) && coords.length >= 2) {
        return {
          lat: Number(coords[1]),
          lon: Number(coords[0]),
          label: suggestion.text,
        }
      }
    } catch {
      // try next endpoint
    }
  }
  throw new Error('Kunne ikke finde koordinater for den valgte adresse.')
}
