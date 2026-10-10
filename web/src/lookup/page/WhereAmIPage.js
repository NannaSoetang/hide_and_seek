import '../../ui/style.css'
import './where-am-i.css'
import { AdministrativeLookup } from '../admin/AdministrativeLookup.js'
import { getCurrentPosition } from '../address/GeolocationService.js'
import { resolveAddressToCoordinates, searchAddresses } from '../address/AddressService.js'
import { Tabs } from '../../ui/Tabs.js'
import { getAppContent } from '../../config/app-content.js'
import { bindLanguageControls, getLocale, setLocale, translateStaticContent } from '../../config/language.js'

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
    bindLanguageControls()
    setLocale(getLocale())
    this.updateStaticContent()
    document.addEventListener('localechange', () => {
      this.updateStaticContent()
      this.elements.locationStatus.textContent = ''
      this.elements.addressStatus.textContent = ''
    })
    this.tabs.bind()
    this.bindLocationTab()
    this.bindAddressTab()
  }

  get UI() {
    return getAppContent(getLocale()).whereAmIPage
  }

  updateStaticContent() {
    const content = getAppContent(getLocale())
    translateStaticContent(content)
    document.title = content.whereAmIPage.title
  }

  async getLookup() {
    if (!this.lookupPromise) {
      this.lookupPromise = AdministrativeLookup.create()
        .catch((error) => {
          this.lookupPromise = null
          throw error
        })
    }
    return this.lookupPromise
  }

  bindLocationTab() {
    this.elements.locationButton.addEventListener('click', async () => {
      this.elements.locationStatus.textContent = this.UI.statuses.findingLocation
      try {
        const position = await getCurrentPosition()
        const lat = position.coords.latitude
        const lon = position.coords.longitude
        const accuracy = position.coords.accuracy
        const hasMatch = await this.applyLookupResult({ lat, lon, addressLabel: null })
        this.elements.locationStatus.textContent = hasMatch
          ? accuracy > 80
            ? this.UI.statuses.lowAccuracy
            : this.UI.statuses.locationFound
          : this.UI.statuses.noMatch
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
      this.elements.addressStatus.textContent = this.UI.statuses.addressSearching
      try {
        const suggestions = await searchAddresses(query, { signal: controller.signal })
        if (this.addressSearchController !== controller) return
        this.currentSuggestions = suggestions
        this.renderAddressSuggestions(suggestions)
        this.elements.addressStatus.textContent = suggestions.length
          ? this.UI.statuses.chooseAddress
          : this.UI.statuses.noAddressResults
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
    this.elements.addressStatus.textContent = this.UI.statuses.findingArea
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
        ? this.UI.statuses.addressFound
        : this.UI.statuses.noMatch
    } catch (error) {
      this.elements.addressStatus.textContent = error.message
    }
  }

  async applyLookupResult({ lat, lon, addressLabel }) {
    const lookup = await this.getLookup()
    const result = lookup.lookup(lat, lon)
    const hasMatch = lookup.hasAny(result)

    this.elements.resultMunicipality.textContent = result.municipality || this.UI.emptyState
    this.elements.resultPostalArea.textContent = result.postalArea || this.UI.emptyState
    this.elements.resultParish.textContent = result.parish || this.UI.emptyState
    this.elements.resultConstituency.textContent = result.constituency || this.UI.emptyState
    this.elements.resultAddress.textContent = addressLabel || this.UI.emptyState
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
  console.error('Could not start the Where Am I page.', error)
})
