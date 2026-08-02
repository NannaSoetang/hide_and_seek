function distance(first, second) {
  return Math.hypot(first[0] - second[0], first[1] - second[1])
}

function lineLength(coordinates) {
  return coordinates.slice(1).reduce((total, point, index) => {
    return total + distance(coordinates[index], point)
  }, 0)
}

export function bestLineCoordinates(features, lineId) {
  return features
    .filter((feature) => feature.properties?.line === lineId)
    .map((feature) => feature.geometry?.coordinates || [])
    .filter((coordinates) => coordinates.length > 1)
    .sort((first, second) => lineLength(second) - lineLength(first))[0] || []
}

function projectedMeasure(point, start, end, cumulative) {
  const delta = [end[0] - start[0], end[1] - start[1]]
  const lengthSquared = delta[0] ** 2 + delta[1] ** 2
  const offset = [point[0] - start[0], point[1] - start[1]]
  const ratio = lengthSquared === 0 ? 0 : (offset[0] * delta[0] + offset[1] * delta[1]) / lengthSquared
  const clampedRatio = Math.max(0, Math.min(1, ratio))
  const projection = [start[0] + delta[0] * clampedRatio, start[1] + delta[1] * clampedRatio]
  return { distance: distance(point, projection), measure: cumulative + distance(start, projection) }
}

function stationMeasureOnLine(stationCoordinates, lineCoordinates) {
  let cumulative = 0
  let closest = { distance: Number.POSITIVE_INFINITY, measure: Number.POSITIVE_INFINITY }
  for (let index = 1; index < lineCoordinates.length; index += 1) {
    const start = lineCoordinates[index - 1]
    const end = lineCoordinates[index]
    const candidate = projectedMeasure(stationCoordinates, start, end, cumulative)
    if (candidate.distance < closest.distance) closest = candidate
    cumulative += distance(start, end)
  }
  return closest.measure
}

export function lineStations(stations, lineId) {
  return (stations.features || []).filter((feature) => {
    return (feature.properties?.lines || []).includes(lineId)
  })
}

export function transferNames(metroStations, trainStations) {
  const metroNames = new Set((metroStations.features || []).map(stationName))
  const trainNames = new Set((trainStations.features || []).map(stationName))
  return new Set([...metroNames].filter((name) => trainNames.has(name)))
}

function stationName(feature) {
  return feature.properties?.name
}

function createSvgElement(tagName, attributes = {}) {
  const element = document.createElementNS('http://www.w3.org/2000/svg', tagName)
  for (const [name, value] of Object.entries(attributes)) {
    element.setAttribute(name, String(value))
  }
  return element
}

function splitStationLabel(name) {
  const words = String(name || '').split(/\s+/).filter(Boolean)
  if (words.length <= 2 || words.join(' ').length <= 14) return [words.join(' ')]
  const halfway = Math.ceil(words.length / 2)
  return [words.slice(0, halfway).join(' '), words.slice(halfway).join(' ')]
}

function orderedStations(stations, lineCoordinates) {
  return [...stations].sort((first, second) => {
    const firstMeasure = stationMeasureOnLine(first.geometry.coordinates, lineCoordinates)
    const secondMeasure = stationMeasureOnLine(second.geometry.coordinates, lineCoordinates)
    return firstMeasure - secondMeasure
  })
}

function createHeader(meta) {
  const header = document.createElement('div')
  header.className = 'guide-line-diagram-header'
  const title = document.createElement('h3')
  title.style.setProperty('--line-color', meta.color)
  title.textContent = meta.title
  const route = document.createElement('p')
  route.textContent = meta.route
  header.append(title, route)
  return header
}

function createDiagramSvg(meta, stationCount) {
  const width = Math.max(760, stationCount * 118)
  const svg = createSvgElement('svg', {
    viewBox: `0 0 ${width} 148`, width, height: 148, role: 'img',
    'aria-label': `${meta.title} ${meta.route}`,
  })
  svg.classList.add('guide-line-diagram-svg')
  return { svg, width }
}

function appendBaseLine(svg, color, width) {
  svg.append(createSvgElement('line', {
    x1: 46, y1: 72, x2: width - 46, y2: 72,
    stroke: color, 'stroke-width': 7, 'stroke-linecap': 'round',
  }))
}

function appendMarker(svg, x, color, isTransfer) {
  svg.append(createSvgElement('circle', {
    cx: x, cy: 72, r: 8, fill: '#ffffff',
    stroke: isTransfer ? '#835900' : color, 'stroke-width': 3,
  }))
}

function appendTie(svg, x, labelTop, isAbove) {
  svg.append(createSvgElement('line', {
    x1: x, y1: 72 + (isAbove ? -12 : 12), x2: x,
    y2: isAbove ? labelTop + 18 : labelTop - 14,
    stroke: '#cad5e4', 'stroke-width': 1.2,
  }))
}

function appendLabel(svg, x, labelTop, lines, isTransfer) {
  const text = createSvgElement('text', {
    x, y: labelTop, 'text-anchor': 'middle',
    class: isTransfer ? 'guide-line-label is-transfer' : 'guide-line-label',
  })
  lines.forEach((line, index) => {
    const span = createSvgElement('tspan', { x, dy: index === 0 ? 0 : 13 })
    span.textContent = line
    text.append(span)
  })
  svg.append(text)
}

function appendStation(svg, station, index, x, meta, transfers) {
  const name = stationName(station)
  const lines = splitStationLabel(name)
  const isAbove = index % 2 === 0
  const labelTop = isAbove ? 24 : 118
  const isTransfer = transfers.has(name)
  appendMarker(svg, x, meta.color, isTransfer)
  if (lines.length > 1) appendTie(svg, x, labelTop, isAbove)
  appendLabel(svg, x, labelTop, lines, isTransfer)
}

function stationPosition(index, stationCount, width) {
  if (stationCount === 1) return width / 2
  return 46 + ((width - 92) / (stationCount - 1)) * index
}

export function renderLineDiagram({ parent, meta, stations, lineCoordinates, transfers }) {
  const ordered = orderedStations(stations, lineCoordinates)
  const diagram = document.createElement('article')
  diagram.className = 'guide-line-diagram'
  const scroller = document.createElement('div')
  scroller.className = 'guide-line-diagram-scroll'
  const { svg, width } = createDiagramSvg(meta, ordered.length)
  appendBaseLine(svg, meta.color, width)
  ordered.forEach((station, index) => {
    const x = stationPosition(index, ordered.length, width)
    appendStation(svg, station, index, x, meta, transfers)
  })
  scroller.append(svg)
  diagram.append(createHeader(meta), scroller)
  parent.append(diagram)
}