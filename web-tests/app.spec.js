import { expect, test } from '@playwright/test'

async function waitForMapReady(page) {
  await expect(page.locator('body')).toHaveAttribute('data-app-ready', 'true')
}

async function waitForGuideReady(page) {
  await expect(page.locator('body')).toHaveAttribute('data-guide-ready', 'true')
}

async function waitForWhereReady(page) {
  await expect(page.locator('body')).toHaveAttribute('data-page-ready', 'true')
}

async function clickExposedTransitLine(page) {
  const point = await page.locator('path.transit-line').evaluateAll((paths) => {
    for (const path of paths) {
      const middle = path.getPointAtLength(path.getTotalLength() / 2)
      const screen = new DOMPoint(middle.x, middle.y).matrixTransform(path.getScreenCTM())
      if (document.elementFromPoint(screen.x, screen.y) === path) return screen.toJSON()
    }
    throw new Error('No exposed transit line segment available')
  })
  await page.mouse.click(point.x, point.y)
}

test('interactive map loads title, links, and map container', async ({ page }) => {
  await page.goto('/')
  await waitForMapReady(page)

  await expect(page.getByRole('heading', { name: 'Hide and Seek' })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Hvor er jeg?' })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Spilguide' })).toBeVisible()
  await expect(page.locator('#map')).toBeVisible()
})

test('interactive map can open station context popup', async ({ page }) => {
  await page.goto('/')
  await waitForMapReady(page)

  await page.evaluate(() => {
    const stationLayer = window.__appDebug?.transportLayers?.metro?.stationLayer
    const firstStation = stationLayer?.getLayers?.()?.[0]
    if (!firstStation) throw new Error('No metro station layer available')
    firstStation.fire('click')
  })

  await expect(page.locator('.leaflet-popup-content')).toContainText('Station:')
})

test('interactive map can select a transit line', async ({ page }) => {
  await page.goto('/')
  await waitForMapReady(page)

  await clickExposedTransitLine(page)
  const selectedLine = await page.evaluate(() => window.__appDebug.map.__selectedTransitLine)

  expect(selectedLine?.network).toBeTruthy()
  await expect(page.locator('path.transit-line[stroke-width="12"]').first()).toBeVisible()
  await expect(page.getByRole('button', { name: 'Ryd linje- og lagfiltrering' })).toBeEnabled()
})

for (const selectedNetwork of ['metro', 's-tog']) {
  test(`line selection styles Metro and S-train consistently when selecting ${selectedNetwork}`, async ({ page }) => {
    await page.goto('/')
    await waitForMapReady(page)

    const styles = await page.evaluate((network) => {
      const transportLayers = window.__appDebug.transportLayers
      const selectedLayer = transportLayers[network].lineLayer.getLayers()[0]
      selectedLayer.fire('click')

      const selectedLine = selectedLayer.feature.properties.line
      return Object.fromEntries(Object.entries(transportLayers).map(([layerNetwork, layers]) => {
        const collect = layer => layer.getLayers().map(featureLayer => ({
          selected: layerNetwork === network && featureLayer.feature.properties.line === selectedLine,
          color: featureLayer.options.color,
          weight: featureLayer.options.weight,
          opacity: featureLayer.options.opacity,
        }))
        return [layerNetwork, {
          lines: collect(layers.lineLayer),
          casings: collect(layers.lineCasingLayer),
        }]
      }))
    }, selectedNetwork)

    for (const networkStyles of Object.values(styles)) {
      for (const line of networkStyles.lines) {
        if (line.selected) {
          expect(line.color.toLowerCase()).not.toBe('#c8d0dc')
        } else {
          expect(line.color.toLowerCase()).toBe('#c8d0dc')
        }
        expect(line.weight).toBe(line.selected ? 12 : 7)
        expect(line.opacity).toBe(line.selected ? 1 : 0.95)
      }
      for (const casing of networkStyles.casings) {
        expect(casing.weight).toBe(casing.selected ? 16 : 11)
        expect(casing.opacity).toBe(0.95)
      }
    }
  })
}

test('stations remain above lines after switching the selected network', async ({ page }) => {
  await page.goto('/')
  await waitForMapReady(page)

  const paneState = await page.evaluate(() => {
    const { map, transportLayers } = window.__appDebug
    transportLayers.metro.lineLayer.getLayers()[0].fire('click')
    transportLayers['s-tog'].lineLayer.getLayers()[0].fire('click')

    return {
      overlayZIndex: Number.parseInt(getComputedStyle(map.getPane('overlayPane')).zIndex, 10),
      stationZIndex: Number.parseInt(getComputedStyle(map.getPane('transitStationPane')).zIndex, 10),
      stationPanes: Object.values(transportLayers).flatMap(({ stationLayer }) => (
        stationLayer.getLayers().flatMap(layer => layer.getLayers().map(marker => marker.options.pane))
      )),
    }
  })

  expect(paneState.stationZIndex).toBeGreaterThan(paneState.overlayZIndex)
  expect(new Set(paneState.stationPanes)).toEqual(new Set(['transitStationPane']))
})

test('where-am-i page loads and tabs can switch', async ({ page }) => {
  const administrativeRequests = []
  page.on('request', (request) => {
    if (/\/(municipalities|postnumre|sogne|opstillingskredse)\.geojson$/.test(request.url())) {
      administrativeRequests.push(request.url())
    }
  })

  await page.goto('/where-am-i.html')
  await waitForWhereReady(page)

  await expect(page.getByRole('heading', { name: 'Hvor er jeg?' })).toBeVisible()
  await expect(page.locator('#panel-location')).toBeVisible()
  expect(administrativeRequests).toEqual([])

  await page.getByRole('tab', { name: 'Adresse' }).click()
  await expect(page.locator('#panel-address')).toBeVisible()
  await expect(page.locator('#panel-location')).toHaveClass(/is-hidden/)

  await page.getByRole('tab', { name: 'Adresse' }).press('ArrowLeft')
  await expect(page.getByRole('tab', { name: 'Min placering' })).toBeFocused()
  await expect(page.locator('#panel-location')).toBeVisible()
})

test('where-am-i reports an unmatched geolocation as a failure', async ({ page, context }) => {
  await context.grantPermissions(['geolocation'], { origin: 'http://127.0.0.1:4173' })
  await context.setGeolocation({ latitude: 0, longitude: 0 })
  await page.goto('/where-am-i.html')
  await waitForWhereReady(page)

  await page.getByRole('button', { name: 'Find min placering' }).click()

  await expect(page.locator('#location-status')).toHaveText(
    'Vi kunne ikke matche placeringen til et administrativt område.',
  )
})

test('where-am-i distinguishes address provider failure from no results', async ({ page }) => {
  await page.route('https://api.dataforsyningen.dk/**', (route) => route.abort())
  await page.goto('/where-am-i.html')
  await waitForWhereReady(page)
  await page.getByRole('tab', { name: 'Adresse' }).click()

  await page.locator('#address-query').fill('Rådhuspladsen')

  await expect(page.locator('#address-status')).toHaveText(
    'Adressesøgning er midlertidigt utilgængelig. Prøv igen senere.',
  )
})

test('where-am-i ignores stale address responses', async ({ page }) => {
  let releaseOldResponse
  let markOldRequestReceived
  const oldResponseGate = new Promise((resolve) => { releaseOldResponse = resolve })
  const oldRequestReceived = new Promise((resolve) => { markOldRequestReceived = resolve })

  await page.route('https://api.dataforsyningen.dk/**', async (route) => {
    const query = new URL(route.request().url()).searchParams.get('q')
    if (query === 'Gammel adresse') {
      markOldRequestReceived()
      await oldResponseGate
    }
    await route.fulfill({
      json: [{ tekst: query === 'Gammel adresse' ? 'Gammelt resultat' : 'Nyt resultat', x: 12, y: 55 }],
    }).catch(() => {})
  })

  await page.goto('/where-am-i.html')
  await waitForWhereReady(page)
  await page.getByRole('tab', { name: 'Adresse' }).click()
  const input = page.locator('#address-query')
  await input.fill('Gammel adresse')
  await oldRequestReceived
  await input.fill('Ny adresse')
  await expect(page.getByRole('option', { name: 'Nyt resultat' })).toBeVisible()

  releaseOldResponse()
  await expect(page.getByRole('option', { name: 'Gammelt resultat' })).toHaveCount(0)
})

test('guide page loads station groups and tabs', async ({ page }, testInfo) => {
  await page.goto('/guide.html')
  await waitForGuideReady(page)

  await expect(page.getByRole('heading', { name: 'Spilguide' })).toBeVisible()
  await expect(page.locator('#station-groups .guide-line-diagram').first()).toBeVisible()

  await page.getByRole('tab', { name: 'Regler' }).click()
  await expect(page.locator('#guide-panel-rules')).toBeVisible()

  await page.getByRole('tab', { name: 'Spørgsmål' }).click()
  await expect(page.locator('#guide-panel-questions')).toBeVisible()

  if (testInfo.project.name === 'phone') {
    const cards = page.locator('#guide-panel-questions .guide-mini-card')
    const firstCard = await cards.nth(0).boundingBox()
    const secondCard = await cards.nth(1).boundingBox()

    expect(secondCard.y).toBeGreaterThan(firstCard.y + firstCard.height)
    expect(await page.locator('body').evaluate((body) => body.scrollWidth)).toBeLessThanOrEqual(
      await page.locator('body').evaluate((body) => body.clientWidth),
    )
  }
})
