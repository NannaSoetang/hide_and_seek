import { getAppContent } from '../../config/app-content.js'
import { getLocale } from '../../config/language.js'

function geolocationErrorMessage(error) {
  const statuses = getAppContent(getLocale()).whereAmIPage.statuses
  if (!error) return statuses.geoUnknown
  if (error.code === 1) {
    return statuses.geoPermissionDenied
  }
  if (error.code === 2) {
    return statuses.geoUnavailable
  }
  if (error.code === 3) {
    return statuses.geoTimeout
  }
  return statuses.geoUnknown
}

export function getCurrentPosition() {
  return new Promise((resolve, reject) => {
    if (!('geolocation' in navigator)) {
      reject(new Error(getAppContent(getLocale()).whereAmIPage.statuses.geoNotSupported))
      return
    }

    navigator.geolocation.getCurrentPosition(
      (position) => resolve(position),
      (error) => reject(new Error(geolocationErrorMessage(error))),
      {
        enableHighAccuracy: true,
        timeout: 12000,
        maximumAge: 3000,
      },
    )
  })
}
