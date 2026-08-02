import './style.css'
import './where-am-i.css'
import {
  AdministrativeLookup,
  getCurrentPosition,
  resolveAddressToCoordinates,
  searchAddresses,
} from './LookupService.js'
import { Tabs } from './Tabs.js'

function debounce(fn, delay = 220) {
  let timer = null
  return (...args) => {
    if (timer) clearTimeout(timer)
    timer = setTimeout(() => fn(...args), delay)
  }
}

function formatCoord(value) {
  return Number(value).toFixed(6)
}

export class WhereAmIPage {
  constructor() {
    this.lookup = null
    this.lookupPromise = null
    this.addressSearchController = null
    this.currentSuggestions = []

    this.elements = {
      tabLocation: document.querySelector('#tab-location'),
      tabAddress: document.querySelector('#tab-address'),
      panelLocation: document.querySelector('#panel-location'),
      panelAddress: document.querySelector('#panel-address'),
      locationButton: document.querySelector('#find-location-button'),
      locationStatus: document.querySelector('#location-status'),
      addressStatus: document.querySelector('#address-status'),
      addressQuery: document.querySelector('#address-query'),
      addressResults: document.querySelector('#address-results'),
      resultMunicipality: document.querySelector('#result-municipality'),
      resultPostalArea: document.querySelector('#result-postal-area'),
      resultParish: document.querySelector('#result-parish'),
      resultConstituency: document.querySelector('#result-constituency'),
      resultAddress: document.querySelector('#result-address'),
      resultCoordinates: document.querySelector('#result-coordinates'),
    }
    this.tabs = new Tabs([
      { id: 'location', tab: this.elements.tabLocation, panel: this.elements.panelLocation },
      { id: 'address', tab: this.elements.tabAddress, panel: this.elements.panelAddress },
    ], {
      onShow: (tab) => {
        if (tab === 'address') this.elements.addressQuery.focus()
      },
    })
  }

  async init() {
    this.tabs.bind()
    this.bindLocationTab()
    this.bindAddressTab()
  }

  async getLookup() {
    if (!this.lookupPromise) {
      this.lookupPromise = AdministrativeLookup.create()
        .then((lookup) => {
          this.lookup = lookup
          return lookup
        })
        .catch((error) => {
          this.lookupPromise = null
          throw error
        })
    }
    return this.lookupPromise
  }

  bindLocationTab() {
    this.elements.locationButton.addEventListener('click', async () => {
      this.elements.locationStatus.textContent = 'Finder din placering...'
      try {
        const position = await getCurrentPosition()
        const lat = position.coords.latitude
        const lon = position.coords.longitude
        const accuracy = position.coords.accuracy
        const hasMatch = await this.applyLookupResult({ lat, lon, addressLabel: null })
        this.elements.locationStatus.textContent = hasMatch
          ? accuracy > 80
            ? 'Placering fundet. Nøjagtigheden er lav, så resultatet kan være omtrentligt.'
            : 'Placering fundet.'
          : 'Vi kunne ikke matche placeringen til et administrativt område.'
      } catch (error) {
        this.elements.locationStatus.textContent = error.message
      }
    })
  }

  bindAddressTab() {
    const runSearch = debounce(async (query) => {
      if (!query || query.trim().length < 3) {
        this.currentSuggestions = []
        this.renderAddressSuggestions([])
        this.elements.addressStatus.textContent = ''
        return
      }

      const controller = new AbortController()
      this.addressSearchController = controller
      this.elements.addressStatus.textContent = 'Søger adresser...'
      try {
        const suggestions = await searchAddresses(query, { signal: controller.signal })
        if (this.addressSearchController !== controller) return
        this.currentSuggestions = suggestions
        this.renderAddressSuggestions(suggestions)
        this.elements.addressStatus.textContent = suggestions.length
          ? 'Vælg en adresse fra listen.'
          : 'Ingen adresser fundet.'
      } catch (error) {
        if (error.name === 'AbortError') return
        this.currentSuggestions = []
        this.renderAddressSuggestions([])
        this.elements.addressStatus.textContent = error.message
      }
    })

    this.elements.addressQuery.addEventListener('input', (event) => {
      this.addressSearchController?.abort()
      this.addressSearchController = null
      runSearch(event.target.value)
    })
  }

  renderAddressSuggestions(suggestions) {
    this.elements.addressResults.replaceChildren(
      ...suggestions.map((item, index) => {
        const button = document.createElement('button')
        button.type = 'button'
        button.className = 'address-option'
        button.role = 'option'
        button.textContent = item.text
        button.addEventListener('click', () => this.selectAddress(index))
        return button
      }),
    )
  }

  async selectAddress(index) {
    const selected = this.currentSuggestions[index]
    if (!selected) return
    this.elements.addressStatus.textContent = 'Finder områdeoplysninger...'
    try {
      const resolved = await resolveAddressToCoordinates(selected)
      this.elements.addressQuery.value = resolved.label
      this.renderAddressSuggestions([])
      const hasMatch = await this.applyLookupResult({
        lat: resolved.lat,
        lon: resolved.lon,
        addressLabel: resolved.label,
      })
      this.elements.addressStatus.textContent = hasMatch
        ? 'Adresse fundet.'
        : 'Vi kunne ikke matche adressen til et administrativt område.'
    } catch (error) {
      this.elements.addressStatus.textContent = error.message
    }
  }

  async applyLookupResult({ lat, lon, addressLabel }) {
    const lookup = await this.getLookup()
    const result = lookup.lookup(lat, lon)
    const hasMatch = lookup.hasAny(result)

    this.elements.resultMunicipality.textContent = result.municipality || '-'
    this.elements.resultPostalArea.textContent = result.postalArea || '-'
    this.elements.resultParish.textContent = result.parish || '-'
    this.elements.resultConstituency.textContent = result.constituency || '-'
    this.elements.resultAddress.textContent = addressLabel || 'Fra din placering'
    this.elements.resultCoordinates.textContent = `${formatCoord(lat)}, ${formatCoord(lon)}`

    return hasMatch
  }
}

async function init() {
  const page = new WhereAmIPage()
  await page.init()
  document.body.dataset.pageReady = 'true'
}

init().catch((error) => {
  console.error('Kunne ikke starte Hvor er jeg?-siden.', error)
})
