import './style.css'
import {
  AdministrativeLookup,
  getCurrentPosition,
  resolveAddressToCoordinates,
  searchAddresses,
} from './LookupService.js'

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
  }

  async init() {
    this.lookup = await AdministrativeLookup.create()
    this.bindTabs()
    this.bindLocationTab()
    this.bindAddressTab()
  }

  bindTabs() {
    this.elements.tabLocation.addEventListener('click', () => this.showTab('location'))
    this.elements.tabAddress.addEventListener('click', () => this.showTab('address'))
  }

  showTab(tab) {
    const isLocation = tab === 'location'
    this.elements.tabLocation.classList.toggle('is-active', isLocation)
    this.elements.tabLocation.setAttribute('aria-selected', String(isLocation))
    this.elements.tabAddress.classList.toggle('is-active', !isLocation)
    this.elements.tabAddress.setAttribute('aria-selected', String(!isLocation))
    this.elements.panelLocation.classList.toggle('is-hidden', !isLocation)
    this.elements.panelAddress.classList.toggle('is-hidden', isLocation)
    if (!isLocation) this.elements.addressQuery.focus()
  }

  bindLocationTab() {
    this.elements.locationButton.addEventListener('click', async () => {
      this.elements.locationStatus.textContent = 'Finder din placering...'
      try {
        const position = await getCurrentPosition()
        const lat = position.coords.latitude
        const lon = position.coords.longitude
        const accuracy = position.coords.accuracy
        this.applyLookupResult({ lat, lon, addressLabel: null, accuracy })
        this.elements.locationStatus.textContent = accuracy > 80
          ? 'Placering fundet. Nøjagtigheden er lav, så resultatet kan være omtrentligt.'
          : 'Placering fundet.'
      } catch (error) {
        this.elements.locationStatus.textContent = error.message
      }
    })
  }

  bindAddressTab() {
    const runSearch = debounce(async (query) => {
      if (!query || query.trim().length < 3) {
        this.renderAddressSuggestions([])
        return
      }
      this.elements.addressStatus.textContent = 'Søger adresser...'
      const suggestions = await searchAddresses(query)
      this.currentSuggestions = suggestions
      this.renderAddressSuggestions(suggestions)
      this.elements.addressStatus.textContent = suggestions.length
        ? 'Vælg en adresse fra listen.'
        : 'Ingen adresser fundet.'
    })

    this.elements.addressQuery.addEventListener('input', (event) => {
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
      this.applyLookupResult({
        lat: resolved.lat,
        lon: resolved.lon,
        addressLabel: resolved.label,
        accuracy: null,
      })
      this.elements.addressStatus.textContent = 'Adresse fundet.'
    } catch (error) {
      this.elements.addressStatus.textContent = error.message
    }
  }

  applyLookupResult({ lat, lon, addressLabel, accuracy }) {
    const result = this.lookup.lookup(lat, lon)
    const hasMatch = this.lookup.hasAny(result)

    this.elements.resultMunicipality.textContent = result.municipality || '-'
    this.elements.resultPostalArea.textContent = result.postalArea || '-'
    this.elements.resultParish.textContent = result.parish || '-'
    this.elements.resultConstituency.textContent = result.constituency || '-'
    this.elements.resultAddress.textContent = addressLabel || 'Fra din placering'
    this.elements.resultCoordinates.textContent = `${formatCoord(lat)}, ${formatCoord(lon)}`

    if (!hasMatch) {
      const message = 'Vi kunne ikke matche placeringen til et administrativt område.'
      this.elements.locationStatus.textContent = message
      this.elements.addressStatus.textContent = message
    }

    if (accuracy && Number.isFinite(accuracy) && accuracy > 80) {
      this.elements.locationStatus.textContent = 'Placering fundet. Nøjagtigheden er lav, så resultatet kan være omtrentligt.'
    }
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
