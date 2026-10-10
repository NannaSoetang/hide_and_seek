const COMMON = {
  app: { title: 'Hide and Seek', pageTitle: 'Hide and Seek' },
  mapPage: {
    title: 'Hide and Seek',
    topbarLabel: 'Application controls',
    quickLink: { text: 'Where Am I?', ariaLabel: 'Go to Where Am I page' },
    map: { ariaLabel: 'Map of Metro and S-train lines and stations' },
    controls: { clearFilter: { text: 'Clear filter', ariaLabel: 'Clear line and layer filtering' } },
    popup: { station: 'Station', lines: 'Lines' },
    status: { loading: 'Loading map...', error: 'Map unavailable. Please refresh the page and try again.' },
    tooltip: { line: 'line' },
  },
  whereAmIPage: {
    title: 'Where am I?',
    backLink: { text: 'Back to map', ariaLabel: 'Back to map' },
    tabs: { location: 'My location', address: 'Address' },
    tabsLabel: 'Choose lookup type',
    addressSuggestionsLabel: 'Address suggestions',
    buttons: { findLocation: 'Find my location' },
    emptyState: '−',
    result: 'Result',
    fields: { municipality: 'Municipality', constituency: 'Constituency', postalArea: 'Postal area', parish: 'Parish', address: 'Address', coordinates: 'Coordinates' },
    placeholders: { addressQuery: 'Search street, number or postal area' },
    statuses: {
      findingLocation: 'Finding your location...', locationFound: 'Location found.',
      lowAccuracy: 'Location found. Accuracy is low, so the result may be approximate.',
      noMatch: 'We could not match the location to an administrative area.',
      addressSearching: 'Searching addresses...', chooseAddress: 'Choose an address from the list.',
      noAddressResults: 'No addresses found.', findingArea: 'Finding area information...', addressFound: 'Address found.',
      addressUnavailable: 'Address search is temporarily unavailable. Please try again later.',
      addressCoordinatesMissing: 'Could not find coordinates for the selected address.',
      geoNotSupported: 'Your browser does not support geolocation.',
      geoPermissionDenied: 'Location access is blocked. Allow location access in your browser settings and try again.',
      geoUnavailable: 'Location is temporarily unavailable. Please try again in a moment.',
      geoTimeout: 'Location lookup took too long. Try again with a stronger signal.',
      geoUnknown: 'Could not retrieve your location.',
    },
  },
  language: { label: 'Language' },
}

const DANISH = {
  ...COMMON,
  mapPage: {
    ...COMMON.mapPage,
    topbarLabel: 'Programstyring',
    quickLink: { text: 'Hvor er jeg?', ariaLabel: 'Gå til Hvor er jeg?' },
    map: { ariaLabel: 'Kort over metro- og S-togslinjer og stationer' },
    controls: { clearFilter: { text: 'Ryd filtrering', ariaLabel: 'Ryd linje- og lagfiltrering' } },
    popup: { station: 'Station', lines: 'Linjer' },
    status: { loading: 'Indlæser kort...', error: 'Kortet kunne ikke indlæses. Genindlæs siden for at prøve igen.' },
    tooltip: { line: 'linje' },
  },
  whereAmIPage: {
    ...COMMON.whereAmIPage,
    title: 'Hvor er jeg?',
    backLink: { text: 'Tilbage til kortet', ariaLabel: 'Tilbage til kortet' },
    tabs: { location: 'Min placering', address: 'Adresse' },
    tabsLabel: 'Vælg opslagstype',
    addressSuggestionsLabel: 'Adresseforslag',
    buttons: { findLocation: 'Find min placering' },
    result: 'Resultat',
    fields: { municipality: 'Kommune', constituency: 'Opstillingskreds', postalArea: 'Postområde', parish: 'Sogn', address: 'Adresse', coordinates: 'Koordinater' },
    placeholders: { addressQuery: 'Søg efter vej, husnummer eller postområde' },
    statuses: {
      findingLocation: 'Finder din placering...', locationFound: 'Placering fundet.',
      lowAccuracy: 'Placering fundet. Nøjagtigheden er lav, så resultatet kan være upræcist.',
      noMatch: 'Vi kunne ikke matche placeringen til et administrativt område.',
      addressSearching: 'Søger efter adresser...', chooseAddress: 'Vælg en adresse fra listen.',
      noAddressResults: 'Ingen adresser fundet.', findingArea: 'Finder områdeinformation...', addressFound: 'Adresse fundet.',
      addressUnavailable: 'Adressesøgning er midlertidigt utilgængelig. Prøv igen senere.',
      addressCoordinatesMissing: 'Kunne ikke finde koordinater for den valgte adresse.',
      geoNotSupported: 'Din browser understøtter ikke positionsbestemmelse.',
      geoPermissionDenied: 'Adgang til din placering er blokeret. Tillad adgang i browserindstillingerne, og prøv igen.',
      geoUnavailable: 'Placeringen er midlertidigt utilgængelig. Prøv igen om lidt.',
      geoTimeout: 'Søgningen efter din placering tog for lang tid. Prøv igen med et stærkere signal.',
      geoUnknown: 'Din placering kunne ikke hentes.',
    },
  },
  language: { label: 'Sprog' },
}

export const APP_CONTENT = { da: DANISH, en: COMMON }

export function getAppContent(locale = 'da') {
  return APP_CONTENT[locale] || APP_CONTENT.da
}
