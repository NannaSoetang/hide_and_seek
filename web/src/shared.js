import L from 'leaflet'

function assetUrl(path) {
  const normalizedBase = import.meta.env.BASE_URL || '/'
  const normalizedPath = path.replace(/^\//, '')
  return `${normalizedBase}${normalizedPath}`
}

const ROUTE_PALETTE = ['#2155cc', '#cc5a00', '#00875a', '#7a3cff', '#c0392b', '#0089a7', '#a65e2e', '#d81b60', '#2e7d32', '#6d4c41']

export function routeColor(label) {
  const text = String(label || '')
  let hash = 0
  for (let index = 0; index < text.length; index += 1) {
    hash = ((hash << 5) - hash + text.charCodeAt(index)) >>> 0
  }
  return ROUTE_PALETTE[hash % ROUTE_PALETTE.length]
}

export async function loadJson(path) {
  const response = await fetch(assetUrl(path))
  if (!response.ok) throw new Error(`Kunne ikke hente ${path}`)
  return response.json()
}

// TODO: Add future datasets through separate, opt-in loaders.
export function loadBoundary() {
  return loadJson('/data/boundary.geojson')
}

export async function loadBaseData() {
  const [boundary, routes, stops, sogne, afstemningsomraader, metadata] = await Promise.all([
    loadJson('/data/boundary.geojson'),
    loadJson('/data/routes.geojson'),
    loadJson('/data/eligible-stops.geojson'),
    loadJson('/data/sogne.geojson'),
    loadJson('/data/afstemningsomraader.geojson'),
    loadJson('/data/metadata.json'),
  ])
  return { boundary, routes, stops, sogne, afstemningsomraader, metadata }
}

export function createBaseMap(elementId, options = {}) {
  const map = L.map(elementId, {
    zoomControl: options.zoomControl ?? true,
    zoomSnap: options.zoomSnap,
    zoomDelta: options.zoomDelta,
  })
  const isDefaultOsm = !options.tileUrl
  L.tileLayer(options.tileUrl || 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: options.attribution || '&copy; OpenStreetMap-bidragsydere',
    maxZoom: options.maxZoom || 19,
    subdomains: options.subdomains || (isDefaultOsm ? 'abc' : undefined),
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

export function addOutsideMask(map, geojson) {
  const boundaryFeature = geojson.features?.[0]
  if (!boundaryFeature) return null

  const rings = []
  if (boundaryFeature.geometry.type === 'Polygon') {
    rings.push(boundaryFeature.geometry.coordinates[0])
  } else if (boundaryFeature.geometry.type === 'MultiPolygon') {
    for (const polygon of boundaryFeature.geometry.coordinates) {
      rings.push(polygon[0])
    }
  }

  const points = rings.flat()
  const xs = points.map((point) => point[0])
  const ys = points.map((point) => point[1])
  const pad = 0.08
  const outerRing = [
    [Math.min(...xs) - pad, Math.min(...ys) - pad],
    [Math.max(...xs) + pad, Math.min(...ys) - pad],
    [Math.max(...xs) + pad, Math.max(...ys) + pad],
    [Math.min(...xs) - pad, Math.max(...ys) + pad],
    [Math.min(...xs) - pad, Math.min(...ys) - pad],
  ]

  const mask = {
    type: 'FeatureCollection',
    features: [
      {
        type: 'Feature',
        properties: {},
        geometry: {
          type: 'Polygon',
          coordinates: [outerRing, ...rings],
        },
      },
    ],
  }

  return L.geoJSON(mask, {
    style: {
      stroke: false,
      fillColor: '#ffffff',
      fillOpacity: 0.5,
    },
    interactive: false,
  }).addTo(map)
}

export function addRoutes(map, geojson) {
  return L.geoJSON(geojson, {
    style: (feature) => ({ color: routeColor(feature.properties.label), weight: 3, opacity: 0.82 }),
    onEachFeature: (feature, layer) => {
      layer.bindPopup(`<strong>Rute ${feature.properties.label}</strong><br>${feature.properties.name}`)
      layer.bindTooltip(`Rute ${feature.properties.label}`, {
        sticky: true,
        direction: 'top',
      })
    },
  }).addTo(map)
}

export function addStops(map, geojson, options = {}) {
  return L.geoJSON(geojson, {
    pointToLayer: (feature, latlng) => {
      const visibleRadius = feature.properties.major ? 4.25 : 2.75
      const hitRadius = options.touchMode
        ? (feature.properties.major ? 13 : 11)
        : (feature.properties.major ? 9 : 8)
      const hitArea = L.circleMarker(latlng, {
        radius: hitRadius,
        color: '#111',
        opacity: 0,
        fillColor: '#111',
        fillOpacity: 0,
        weight: 0,
      })
      const visibleDot = L.circleMarker(latlng, {
        radius: visibleRadius,
        color: '#111',
        fillColor: '#111',
        fillOpacity: 0.95,
        weight: 1,
        interactive: false,
      })
      return L.featureGroup([hitArea, visibleDot])
    },
    onEachFeature: (feature, layer) => {
      layer.bindPopup(`<strong>${feature.properties.name}</strong><br>${feature.properties.events} direkte bushaendelser<br>${feature.properties.nearby_events} bushaendelser inden for 500 m`)
      layer.on('click', () => {
        options.onStopSelect?.(feature)
      })
      if (options.hoverLabels !== false) {
        layer.bindTooltip(feature.properties.name, {
          sticky: true,
          direction: 'top',
        })
      }
      if (options.labelMajors && feature.properties.major) {
        layer.bindTooltip(feature.properties.name, {
          permanent: true,
          direction: 'right',
          offset: [8, 0],
          className: 'major-stop-label',
        })
      }
    },
  }).addTo(map)
}

export function addSogne(map, geojson) {
  const layer = L.geoJSON(geojson, {
    style: {
      color: '#7b68a6',
      weight: 1,
      opacity: 0.65,
      fillColor: '#a78bfa',
      fillOpacity: 0.08,
    },
    onEachFeature: (feature, featureLayer) => {
      const name = feature.properties.navn || feature.properties.name
      if (name) {
        featureLayer.bindTooltip(name, {
          permanent: true,
          direction: 'center',
          className: 'area-label sogn-label',
        })
      }
    },
  })
  layer.addTo(map)
  return layer
}

export function addAfstemningsomraader(map, geojson) {
  return L.geoJSON(geojson, {
    style: {
      color: '#1f7a8c',
      weight: 1,
      opacity: 0.7,
      fillColor: '#67c6d3',
      fillOpacity: 0.07,
    },
    onEachFeature: (feature, featureLayer) => {
      const label = feature.properties.navn || `Område ${feature.properties.nummer}`
      featureLayer.bindTooltip(label, {
        permanent: true,
        direction: 'center',
        className: 'area-label afstemning-label',
      })
      featureLayer.bindPopup(`<strong>${label}</strong><br>Afstemningsområde ${feature.properties.nummer || '-'}`)
    },
  })
}

export function fitAll(map, layers) {
  const bounds = L.featureGroup(layers).getBounds()
  if (bounds.isValid()) map.fitBounds(bounds.pad(0.08))
}

export function fitBoundsWithPadding(map, layer, options = {}) {
  const bounds = layer.getBounds()
  if (!bounds.isValid()) return
  map.fitBounds(bounds, {
    paddingTopLeft: options.paddingTopLeft || [24, 24],
    paddingBottomRight: options.paddingBottomRight || [24, 24],
    maxZoom: options.maxZoom,
  })
}

export function formatAreaValue(value) {
  return value || '-'
}
