import L from 'leaflet'

function assetUrl(path) {
  const base = import.meta.env.BASE_URL || '/'
  return `${base}${path.replace(/^\//, '')}`
}

export async function loadJson(path) {
  const response = await fetch(assetUrl(path))
  if (!response.ok) throw new Error(`Kunne ikke hente ${path}`)
  return response.json()
}

export function loadBoundary() {
  return loadJson('/data/boundary.geojson')
}

export function createBaseMap(elementId, options = {}) {
  const map = L.map(elementId, {
    zoomControl: options.zoomControl ?? true,
    zoomSnap: options.zoomSnap,
    zoomDelta: options.zoomDelta,
  })
  const isOpenStreetMap = !options.tileUrl
  L.tileLayer(options.tileUrl || 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: options.attribution || '&copy; OpenStreetMap-bidragsydere',
    maxZoom: options.maxZoom || 19,
    subdomains: options.subdomains || (isOpenStreetMap ? 'abc' : undefined),
  }).addTo(map)
  return map
}

export function addBoundary(map, geojson) {
  return L.geoJSON(geojson, {
    interactive: false,
    style: {
      color: '#c0392b',
      weight: 3,
      dashArray: '10 6',
      fillOpacity: 0.03,
    },
  }).addTo(map)
}
