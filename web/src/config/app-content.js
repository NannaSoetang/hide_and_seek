export const APP_CONTENT = {
  app: {
    title: 'Hide and Seek',
    pageTitle: 'Hide and Seek',
  },
  mapPage: {
    title: 'Hide and Seek',
    quickLink: {
      text: 'Where Am I?',
      ariaLabel: 'Go to Where Am I page',
    },
    map: {
      ariaLabel: 'Map of Metro and S-train lines and stations',
    },
    controls: {
      clearFilter: {
        text: 'Clear filter',
        ariaLabel: 'Clear line and layer filtering',
      },
    },
  },
  whereAmIPage: {
    title: 'Where Am I?',
    backLink: {
      text: 'Back to map',
      ariaLabel: 'Back to map',
    },
    tabs: {
      location: 'My location',
      address: 'Address',
    },
    buttons: {
      findLocation: 'Find my location',
    },
    emptyState: '−',
    result: 'Result',
    fields: {
      municipality: 'Municipality',
      constituency: 'Constituency',
      postalArea: 'Postal area',
      parish: 'Parish',
      address: 'Address',
      coordinates: 'Coordinates',
    },
    placeholders: {
      addressQuery: 'Search street, number or postal area',
    },
    statuses: {
      findingLocation: 'Finding your location...',
      locationFound: 'Location found.',
      lowAccuracy: 'Location found. Accuracy is low, so the result may be approximate.',
      noMatch: 'We could not match the location to an administrative area.',
      addressSearching: 'Searching addresses...',
      chooseAddress: 'Choose an address from the list.',
      noAddressResults: 'No addresses found.',
      findingArea: 'Finding area information...',
      addressFound: 'Address found.',
    },
  },
}
