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

export function geometryBounds(geometry) {
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

export function pointInBounds(point, bounds) {
  if (!bounds) return false
  return point[0] >= bounds.minX
    && point[0] <= bounds.maxX
    && point[1] >= bounds.minY
    && point[1] <= bounds.maxY
}
