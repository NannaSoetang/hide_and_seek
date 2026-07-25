import './style.css'
import { filterTransportData, loadTransportData } from './transport.js'

const METRO_LINE_META = {
  M1: { title: 'M1', route: 'Vanløse – Vestamager', color: '#00a650', network: 'Metro' },
  M2: { title: 'M2', route: 'Vanløse – Lufthavnen', color: '#f5c400', network: 'Metro' },
  M3: { title: 'M3', route: 'Cityringen', color: '#e03b3b', network: 'Metro' },
  M4: { title: 'M4', route: 'Orientkaj – København Syd', color: '#0072bc', network: 'Metro' },
}

const STOG_LINE_META = {
  A: { title: 'A-linje', route: 'Hillerød – Vallensbæk', color: '#1f4e9e', network: 'S-tog' },
  B: { title: 'B-linje', route: 'Farum – Høje Taastrup', color: '#2f9e44', network: 'S-tog' },
  C: { title: 'C-linje', route: 'Klampenborg – Frederikssund', color: '#f28e2b', network: 'S-tog' },
  F: { title: 'F-linje', route: 'Hellerup – Ny Ellebjerg', color: '#f2a900', network: 'S-tog' },
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

function renderStationListItem(station, network, transfers) {
  const item = document.createElement('li')
  item.className = 'guide-station-item'

  const name = normalizeStationName(station.properties?.name || '').replace(/^./, (c) => c.toUpperCase())
  const displayName = (station.properties?.name || '').replace(/\s*\(Metro\)\s*/gi, '').trim()
  const isTransfer = transfers.has(name)

  const nameSpan = document.createElement('span')
  nameSpan.className = 'guide-station-name'
  nameSpan.textContent = displayName

  const badges = document.createElement('span')
  badges.className = 'guide-station-badges'

  const networkBadge = document.createElement('span')
  networkBadge.className = 'guide-badge guide-badge-network'
  networkBadge.textContent = network
  badges.append(networkBadge)

  if (isTransfer) {
    const transferBadge = document.createElement('span')
    transferBadge.className = 'guide-badge guide-badge-transfer'
    transferBadge.textContent = 'Skift'
    badges.append(transferBadge)
  }

  item.append(nameSpan, badges)
  return item
}

function renderLineAccordion({ parent, lineKey, meta, stations, lineCoords, transfers }) {
  const details = document.createElement('details')
  details.className = 'guide-line-accordion'

  const summary = document.createElement('summary')
  summary.className = 'guide-line-summary'
  summary.style.setProperty('--line-color', meta.color)
  summary.innerHTML = `<strong>${meta.title}</strong> <span>${meta.route}</span>`

  const list = document.createElement('ol')
  list.className = 'guide-station-list'

  const ordered = [...stations]
    .map((station) => ({
      station,
      measure: stationMeasureOnLine(station.geometry?.coordinates || [0, 0], lineCoords),
    }))
    .sort((a, b) => a.measure - b.measure)
    .map((entry) => entry.station)

  list.replaceChildren(...ordered.map((station) => renderStationListItem(station, meta.network, transfers)))

  details.append(summary, list)
  parent.append(details)
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
      renderLineAccordion({
        parent: container,
        lineKey,
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
      renderLineAccordion({
        parent: container,
        lineKey,
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
