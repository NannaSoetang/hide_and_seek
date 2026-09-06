import transitLines from './transit-lines.json' with { type: 'json' }
import adminLayers from './admin-layers.json' with { type: 'json' }

// Single source of truth for transit line styling and metadata.
// Consumed by the interactive map and the generated transport metadata files.
export const TRANSIT_LINES = transitLines
export const ADMIN_LAYERS = adminLayers
export const TRANSIT_NETWORKS = [...new Set(transitLines.map((line) => line.network))]

export const ADMIN_LAYER_INFO = Object.fromEntries(
  ADMIN_LAYERS.map((layer) => {
    const labels = {
      da: layer.name,
      en: layer.labels?.en || layer.name,
    }
    return [
      layer.id,
      {
        ...layer,
        labels,
        contextLabel: {
          da: layer.context?.da || layer.name,
          en: layer.context?.en || labels.en,
        },
      },
    ]
  }),
)

export function getAdminLayerLabel(layerId, locale = 'da') {
  const metadata = ADMIN_LAYER_INFO[layerId]
  if (!metadata) return layerId
  return metadata.labels?.[locale] || metadata.name || layerId
}

export function getAdminLayerContextLabel(layerId, locale = 'en') {
  const metadata = ADMIN_LAYER_INFO[layerId]
  if (!metadata) return layerId
  return metadata.contextLabel?.[locale] || metadata.labels?.[locale] || metadata.name || layerId
}

export const LINE_COLORS = Object.fromEntries(
  transitLines.map((line) => [line.line, line.color]),
)

export const TRANSIT_LINE_THEME = {
  baseWeight: 7,
  selectedWeight: 12,
  casingWeight: 11,
  normalOpacity: 0.95,
  mutedOpacity: 0.95,
  selectedOpacity: 1,
  stationRadius: 5.5,
  selectedStationRadius: 8.5,
  stationColor: '#172033',
  stationFill: '#ffffff',
  stationSelectionFill: '#ffd54a',
  lineCasingColor: '#ffffff',
  inactiveColor: '#c8d0dc',
}

export function getTransitLineColor(feature) {
  const lineNumber = feature?.properties?.line
  return LINE_COLORS[lineNumber] || feature?.properties?.color || '#6a6a6a'
}

export function buildTransitLineStyle(feature, state = {}) {
  const selected = Boolean(state.selected)
  const hasSelection = Boolean(state.hasSelection)
  const color = getTransitLineColor(feature)

  return {
    color: selected ? color : (hasSelection ? TRANSIT_LINE_THEME.inactiveColor : color),
    opacity: selected ? TRANSIT_LINE_THEME.selectedOpacity : (hasSelection ? TRANSIT_LINE_THEME.mutedOpacity : TRANSIT_LINE_THEME.normalOpacity),
    weight: selected ? TRANSIT_LINE_THEME.selectedWeight : TRANSIT_LINE_THEME.baseWeight,
    fill: false,
    lineCap: 'round',
    lineJoin: 'round',
    smoothFactor: 1.25,
  }
}

export function linesForNetwork(network) {
  return transitLines.filter((line) => line.network === network)
}

export function adminLayerStyle(layer) {
  return {
    color: layer.color,
    fillColor: layer.color,
    weight: 2.8,
    opacity: 0.8,
    fillOpacity: 0.12,
  }
}
