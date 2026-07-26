import './style.css'
import { filterTransportData, loadTransportData } from './transport.js'

const METRO_LINE_META = {
  M1: { title: 'M1', route: 'Vanløse – Vestamager', color: '#00a650', network: 'Metro' },
  M2: { title: 'M2', route: 'Vanløse – Lufthavnen', color: '#f5c400', network: 'Metro' },
  M3: { title: 'M3', route: 'Cityringen', color: '#e03b3b', network: 'Metro' },
  M4: { title: 'M4', route: 'Orientkaj – København Syd', color: '#0072bc', network: 'Metro' },
}

const STOG_LINE_META = {
  A: { title: 'A-linje', route: 'Hillerød – Køge (Tilladt Lyngby - Vallensbæk)', color: '#1f4e9e', network: 'S-tog' },
  B: { title: 'B-linje', route: 'Farum – Høje Taastrup (Tilladt Budding - Glostrup)', color: '#2f9e44', network: 'S-tog' },
  C: { title: 'C-linje', route: 'Klampenborg – Frederikssund (Tilladt Klampenborg - Herlev)', color: '#f28e2b', network: 'S-tog' },
  F: { title: 'F-linje', route: 'Hellerup – København Syd', color: '#f2a900', network: 'S-tog' },
}

function distance(a, b) {
  const dx = a[0] - b[0]
  const dy = a[1] - b[1]
  return Math.hypot(dx, dy)
}

function normalizeStationName(name) {
  return String(name || '')
    .replace(/\s*\(Metro\)\s*/gi, '')
    .replace(/\s+/g, ' ')
    .trim()
    .toLowerCase()
}

function lineLength(coords) {
  let sum = 0
  for (let i = 1; i < coords.length; i += 1) {
    sum += distance(coords[i - 1], coords[i])
  }
  return sum
}

function bestLineCoordinates(features, lineId) {
  const candidates = features
    .filter((f) => f.properties?.line === lineId)
    .map((f) => f.geometry?.coordinates || [])
    .filter((coords) => Array.isArray(coords) && coords.length > 1)
  if (!candidates.length) return []
  return candidates.sort((a, b) => lineLength(b) - lineLength(a))[0]
}

function stationMeasureOnLine(stationCoord, lineCoords) {
  if (!lineCoords.length) return Number.POSITIVE_INFINITY

  let cumulative = 0
  let best = Number.POSITIVE_INFINITY
  let bestMeasure = Number.POSITIVE_INFINITY

  for (let i = 1; i < lineCoords.length; i += 1) {
    const a = lineCoords[i - 1]
    const b = lineCoords[i]
    const abx = b[0] - a[0]
    const aby = b[1] - a[1]
    const apx = stationCoord[0] - a[0]
    const apy = stationCoord[1] - a[1]
    const denom = abx * abx + aby * aby
    const t = denom === 0 ? 0 : Math.max(0, Math.min(1, (apx * abx + apy * aby) / denom))
    const proj = [a[0] + abx * t, a[1] + aby * t]
    const d = distance(stationCoord, proj)

    if (d < best) {
      best = d
      bestMeasure = cumulative + distance(a, proj)
    }
    cumulative += distance(a, b)
  }
  return bestMeasure
}

function lineStations(stations, lineId) {
  return (stations.features || []).filter((feature) => (feature.properties?.lines || []).includes(lineId))
}

function transferNames(metroStations, stogStations) {
  const metro = new Set((metroStations.features || []).map((f) => normalizeStationName(f.properties?.name)))
  const stog = new Set((stogStations.features || []).map((f) => normalizeStationName(f.properties?.name)))
  const transfers = new Set()
  for (const name of metro) {
    if (stog.has(name)) transfers.add(name)
  }
  return transfers
}

function createSvgElement(tagName) {
  return document.createElementNS('http://www.w3.org/2000/svg', tagName)
}

function splitStationLabel(name) {
  const words = String(name || '').split(/\s+/).filter(Boolean)
  if (words.length <= 2 || words.join(' ').length <= 14) return [words.join(' ')]

  const halfway = Math.max(1, Math.ceil(words.length / 2))
  const first = words.slice(0, halfway).join(' ')
  const second = words.slice(halfway).join(' ')
  return second ? [first, second] : [first]
}

function renderLineDiagram({ parent, meta, stations, lineCoords, transfers }) {
  const ordered = [...stations]
    .map((station) => ({
      station,
      measure: stationMeasureOnLine(station.geometry?.coordinates || [0, 0], lineCoords),
    }))
    .sort((a, b) => a.measure - b.measure)
    .map((entry) => entry.station)

  const diagram = document.createElement('article')
  diagram.className = 'guide-line-diagram'

  const header = document.createElement('div')
  header.className = 'guide-line-diagram-header'

  const title = document.createElement('h3')
  title.style.setProperty('--line-color', meta.color)
  title.textContent = meta.title

  const route = document.createElement('p')
  route.textContent = meta.route

  header.append(title, route)

  const scroller = document.createElement('div')
  scroller.className = 'guide-line-diagram-scroll'

  const svgWidth = Math.max(760, ordered.length * 118)
  const svgHeight = 148
  const svg = createSvgElement('svg')
  svg.classList.add('guide-line-diagram-svg')
  svg.setAttribute('viewBox', `0 0 ${svgWidth} ${svgHeight}`)
  svg.setAttribute('width', String(svgWidth))
  svg.setAttribute('height', String(svgHeight))
  svg.setAttribute('role', 'img')
  svg.setAttribute('aria-label', `${meta.title} ${meta.route}`)

  const lineY = 72
  const left = 46
  const right = svgWidth - 46
  const step = ordered.length > 1 ? (right - left) / (ordered.length - 1) : 0

  const baseLine = createSvgElement('line')
  baseLine.setAttribute('x1', String(left))
  baseLine.setAttribute('y1', String(lineY))
  baseLine.setAttribute('x2', String(right))
  baseLine.setAttribute('y2', String(lineY))
  baseLine.setAttribute('stroke', meta.color)
  baseLine.setAttribute('stroke-width', '7')
  baseLine.setAttribute('stroke-linecap', 'round')
  svg.append(baseLine)

  ordered.forEach((station, index) => {
    const stationName = (station.properties?.name || '').replace(/\s*\(Metro\)\s*/gi, '').trim()
    const normalizedName = normalizeStationName(stationName)
    const isTransfer = transfers.has(normalizedName)
    const x = ordered.length > 1 ? left + step * index : svgWidth / 2
    const labelLines = splitStationLabel(stationName)
    const labelTop = index % 2 === 0 ? 24 : 118

    const marker = createSvgElement('circle')
    marker.setAttribute('cx', String(x))
    marker.setAttribute('cy', String(lineY))
    marker.setAttribute('r', '8')
    marker.setAttribute('fill', '#ffffff')
    marker.setAttribute('stroke', isTransfer ? '#835900' : meta.color)
    marker.setAttribute('stroke-width', '3')
    svg.append(marker)

    if (labelLines.length > 1) {
      const tie = createSvgElement('line')
      tie.setAttribute('x1', String(x))
      tie.setAttribute('y1', String(lineY + (index % 2 === 0 ? -12 : 12)))
      tie.setAttribute('x2', String(x))
      tie.setAttribute('y2', String(index % 2 === 0 ? labelTop + 18 : labelTop - 14))
      tie.setAttribute('stroke', '#cad5e4')
      tie.setAttribute('stroke-width', '1.2')
      svg.append(tie)
    }

    const text = createSvgElement('text')
    text.setAttribute('x', String(x))
    text.setAttribute('y', String(labelTop))
    text.setAttribute('text-anchor', 'middle')
    text.setAttribute('class', isTransfer ? 'guide-line-label is-transfer' : 'guide-line-label')

    labelLines.forEach((line, labelIndex) => {
      const tspan = createSvgElement('tspan')
      tspan.setAttribute('x', String(x))
      tspan.setAttribute('dy', labelIndex === 0 ? '0' : '13')
      tspan.textContent = line
      text.append(tspan)
    })

    svg.append(text)
  })

  scroller.append(svg)
  diagram.append(header, scroller)
  parent.append(diagram)
}

export class GuidePage {
  constructor() {
    this.elements = {
      tabStations: document.querySelector('#guide-tab-stations'),
      tabRules: document.querySelector('#guide-tab-rules'),
      tabQuestions: document.querySelector('#guide-tab-questions'),
      panelStations: document.querySelector('#guide-panel-stations'),
      panelRules: document.querySelector('#guide-panel-rules'),
      panelQuestions: document.querySelector('#guide-panel-questions'),
      stationGroups: document.querySelector('#station-groups'),
    }
  }

  bindTabs() {
    this.elements.tabStations.addEventListener('click', () => this.showTab('stations'))
    this.elements.tabRules.addEventListener('click', () => this.showTab('rules'))
    this.elements.tabQuestions.addEventListener('click', () => this.showTab('questions'))
  }

  showTab(tab) {
    const tabState = {
      stations: tab === 'stations',
      rules: tab === 'rules',
      questions: tab === 'questions',
    }

    this.elements.tabStations.classList.toggle('is-active', tabState.stations)
    this.elements.tabRules.classList.toggle('is-active', tabState.rules)
    this.elements.tabQuestions.classList.toggle('is-active', tabState.questions)

    this.elements.tabStations.setAttribute('aria-selected', String(tabState.stations))
    this.elements.tabRules.setAttribute('aria-selected', String(tabState.rules))
    this.elements.tabQuestions.setAttribute('aria-selected', String(tabState.questions))

    this.elements.panelStations.classList.toggle('is-hidden', !tabState.stations)
    this.elements.panelRules.classList.toggle('is-hidden', !tabState.rules)
    this.elements.panelQuestions.classList.toggle('is-hidden', !tabState.questions)
  }

  async renderStations() {
    const transport = await loadTransportData()
    const metro = filterTransportData(transport, 'metro')
    const stog = filterTransportData(transport, 's-tog')

    const transfers = transferNames(metro.stations, stog.stations)
    const container = this.elements.stationGroups
    container.replaceChildren()

    const metroHeader = document.createElement('h3')
    metroHeader.className = 'guide-network-title'
    metroHeader.textContent = 'Metro'
    container.append(metroHeader)

    for (const lineKey of ['M1', 'M2', 'M3', 'M4']) {
      renderLineDiagram({
        parent: container,
        meta: METRO_LINE_META[lineKey],
        stations: lineStations(metro.stations, lineKey),
        lineCoords: bestLineCoordinates(metro.lines.features || [], lineKey),
        transfers,
      })
    }

    const stogHeader = document.createElement('h3')
    stogHeader.className = 'guide-network-title'
    stogHeader.textContent = 'S-tog'
    container.append(stogHeader)

    for (const lineKey of ['A', 'B', 'C', 'F']) {
      renderLineDiagram({
        parent: container,
        meta: STOG_LINE_META[lineKey],
        stations: lineStations(stog.stations, lineKey),
        lineCoords: bestLineCoordinates(stog.lines.features || [], lineKey),
        transfers,
      })
    }
  }

  async init() {
    this.bindTabs()
    await this.renderStations()
  }
}

async function init() {
  const page = new GuidePage()
  await page.init()
  document.body.dataset.guideReady = 'true'
}

init().catch((error) => {
  console.error('Kunne ikke starte Spilguide.', error)
})
