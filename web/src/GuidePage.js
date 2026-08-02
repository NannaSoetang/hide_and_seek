import './style.css'
import './guide.css'
import {
  bestLineCoordinates,
  lineStations,
  renderLineDiagram,
  transferNames,
} from './GuideLineDiagram.js'
import { filterTransportData, loadTransportData } from './transport.js'
import { linesForNetwork } from './theme.js'
import { Tabs } from './Tabs.js'

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
    this.tabs = new Tabs([
      { id: 'stations', tab: this.elements.tabStations, panel: this.elements.panelStations },
      { id: 'rules', tab: this.elements.tabRules, panel: this.elements.panelRules },
      { id: 'questions', tab: this.elements.tabQuestions, panel: this.elements.panelQuestions },
    ])
  }

  async renderStations() {
    const transport = await loadTransportData()
    const metro = filterTransportData(transport, 'metro')
    const stog = filterTransportData(transport, 's-tog')

    const transfers = transferNames(metro.stations, stog.stations)
    const container = this.elements.stationGroups
    container.replaceChildren()

    const networks = [
      {
          id: "metro",
          label: "Metro",
          data: metro,
      },
      {
          id: "s-tog",
          label: "S-tog",
          data: stog,
      },
  ]

    for (const network of networks) {
      const header = document.createElement('h3')
      header.className = 'guide-network-title'
      header.textContent = network.label
      container.append(header)

      for (const meta of linesForNetwork(network.id)) {
        renderLineDiagram({
          parent: container,
          meta,
          stations: lineStations(network.data.stations, meta.line),
          lineCoordinates: bestLineCoordinates(network.data.lines.features || [], meta.line),
          transfers,
        })
      }
    }
  }

  async init() {
    this.tabs.bind()
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
