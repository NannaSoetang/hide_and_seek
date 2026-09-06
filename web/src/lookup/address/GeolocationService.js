function geolocationErrorMessage(error) {
  if (!error) return 'Could not retrieve your location.'
  if (error.code === 1) {
    return 'Location access is blocked. Allow location access in your browser settings and try again.'
  }
  if (error.code === 2) {
    return 'Location is temporarily unavailable. Please try again in a moment.'
  }
  if (error.code === 3) {
    return 'Location lookup took too long. Try again with a stronger signal.'
  }
  return 'Could not retrieve your location.'
}

export function getCurrentPosition() {
  return new Promise((resolve, reject) => {
    if (!('geolocation' in navigator)) {
      reject(new Error('Your browser does not support geolocation.'))
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
