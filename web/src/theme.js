import transitLines from './transit-lines.json'
import adminLayers from './admin-layers.json'

// Single source of truth for transit line styling and metadata.
// Consumed by the interactive map, the guide page, and (via web/src/*.json)
// the Python PDF generators.
export const TRANSIT_LINES = transitLines
export const ADMIN_LAYERS = adminLayers

export const LINE_COLORS = Object.fromEntries(
  transitLines.map((line) => [line.line, line.color]),
)

export function linesForNetwork(network) {
  return transitLines.filter((line) => line.network === network)
}

export function adminLayerStyle(layer) {
  return {
    color: layer.color,
    weight: layer.weight,
    opacity: layer.opacity,
    fillColor: layer.fillColor,
    fillOpacity: layer.fillOpacity,
  }
}
