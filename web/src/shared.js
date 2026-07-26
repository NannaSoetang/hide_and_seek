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
  if (!map.getPane('boundaryFillPane')) {
    map.createPane('boundaryFillPane')
    const fillPane = map.getPane('boundaryFillPane')
    fillPane.style.zIndex = '320'
    fillPane.style.pointerEvents = 'none'
  }

  if (!map.getPane('boundaryOutlinePane')) {
    map.createPane('boundaryOutlinePane')
    const outlinePane = map.getPane('boundaryOutlinePane')
    outlinePane.style.zIndex = '470'
    outlinePane.style.pointerEvents = 'none'
  }

  const fillLayer = L.geoJSON(geojson, {
    pane: 'boundaryFillPane',
    interactive: false,
    style: {
      stroke: false,
      fillColor: '#b31d1d',
      fillOpacity: 0.09,
    },
  })

  const outerStrokeLayer = L.geoJSON(geojson, {
    pane: 'boundaryOutlinePane',
    interactive: false,
    style: {
      color: '#ffffff',
      weight: 8,
      opacity: 0.95,
      fillOpacity: 0,
    },
  })

  const mainStrokeLayer = L.geoJSON(geojson, {
    pane: 'boundaryOutlinePane',
    interactive: false,
    style: {
      color: '#b71c1c',
      weight: 5,
      opacity: 0.96,
      dashArray: '12 7',
      fillOpacity: 0,
    },
  })

  return L.featureGroup([fillLayer, outerStrokeLayer, mainStrokeLayer]).addTo(map)
}
