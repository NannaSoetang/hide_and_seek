// Compatibility exports for callers that still use the original lookup module.
export { AdministrativeLookup } from './admin/AdministrativeLookup.js'
export { getCurrentPosition } from './address/GeolocationService.js'
export { resolveAddressToCoordinates, searchAddresses } from './address/AddressService.js'
export { geometryBounds, pointInBounds, pointInGeometry } from './admin/geometry.js'
