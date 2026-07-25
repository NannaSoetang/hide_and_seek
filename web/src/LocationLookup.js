function geolocationErrorMessage(error) {
  if (!error) return 'Kunne ikke hente din placering.'
  if (error.code === 1) {
    return 'Placering er blokeret. Tillad lokalitet i Safari-indstillinger og prøv igen.'
  }
  if (error.code === 2) {
    return 'Placering er midlertidigt utilgængelig. Prøv igen om et øjeblik.'
  }
  if (error.code === 3) {
    return 'Placering tog for lang tid. Prøv igen med bedre signal.'
  }
  return 'Kunne ikke hente din placering.'
}

export function getCurrentPosition() {
  return new Promise((resolve, reject) => {
    if (!('geolocation' in navigator)) {
      reject(new Error('Din browser understøtter ikke geolokation.'))
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
