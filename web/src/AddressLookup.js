const AUTOCOMPLETE_ENDPOINTS = [
  'https://api.dataforsyningen.dk/adresser/autocomplete',
  'https://api.dataforsyningen.dk/autocomplete',
]

const ADDRESS_DETAIL_ENDPOINTS = [
  'https://api.dataforsyningen.dk/adresser',
]

async function fetchJson(url) {
  const response = await fetch(url)
  if (!response.ok) throw new Error(`HTTP ${response.status}`)
  return response.json()
}

function buildUrl(base, params) {
  const url = new URL(base)
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      url.searchParams.set(key, String(value))
    }
  })
  return url.toString()
}

function toSuggestion(item) {
  if (typeof item === 'string') {
    return { id: null, text: item, lon: null, lat: null }
  }
  const text = item.tekst
    || item.adressebetegnelse
    || item.forslagstekst
    || item.label
    || item.værdi
    || ''

  const id = item.id || item.adresse?.id || null
  const lon = item.x ?? item.adgangsadresse?.adgangspunkt?.koordinater?.[0] ?? null
  const lat = item.y ?? item.adgangsadresse?.adgangspunkt?.koordinater?.[1] ?? null

  return { id, text, lon, lat }
}

export async function searchAddresses(query) {
  if (!query || query.trim().length < 3) return []

  for (const endpoint of AUTOCOMPLETE_ENDPOINTS) {
    try {
      const payload = await fetchJson(buildUrl(endpoint, { q: query, fuzzy: '' }))
      const candidates = Array.isArray(payload)
        ? payload
        : (payload?.resultater || payload?.hits || [])
      const suggestions = candidates.map(toSuggestion).filter((item) => item.text)
      if (suggestions.length) return suggestions.slice(0, 5)
    } catch {
      // try next endpoint
    }
  }
  return []
}

export async function resolveAddressToCoordinates(suggestion) {
  if (suggestion.lat !== null && suggestion.lon !== null) {
    return { lat: Number(suggestion.lat), lon: Number(suggestion.lon), label: suggestion.text }
  }
  if (!suggestion.id) {
    throw new Error('Kunne ikke finde koordinater for den valgte adresse.')
  }

  for (const endpoint of ADDRESS_DETAIL_ENDPOINTS) {
    try {
      const payload = await fetchJson(buildUrl(endpoint, { id: suggestion.id }))
      const item = Array.isArray(payload) ? payload[0] : payload
      const coords = item?.adgangsadresse?.adgangspunkt?.koordinater
      if (Array.isArray(coords) && coords.length >= 2) {
        return {
          lat: Number(coords[1]),
          lon: Number(coords[0]),
          label: suggestion.text,
        }
      }
    } catch {
      // try next endpoint
    }
  }
  throw new Error('Kunne ikke finde koordinater for den valgte adresse.')
}
