import { expect, test } from '@playwright/test'

async function waitForAppReady(page) {
  await expect(page.locator('body')).toHaveAttribute('data-app-ready', 'true')
}

async function openMobilePanelIfNeeded(page, testInfo) {
  if (testInfo.project.name === 'phone') {
    await page.locator('#mobile-panel-toggle').click()
  }
}

test('interactive map loads core UI', async ({ page }) => {
  await page.goto('/')
  await waitForAppReady(page)
  // TODO: Update this test when changing the target region (currently Randers).
  await expect(page.getByRole('heading', { name: 'Randers hide and seek' })).toBeVisible()
  await expect(page.locator('#map')).toBeVisible()
  await expect(page.getByText('Spillegrænse')).toBeVisible()
})

test('print page loads map and header', async ({ page }) => {
  await page.goto('/print.html')
  await expect(page.getByRole('heading', { name: 'Randers hide and seek' })).toBeVisible()
  await expect(page.locator('#print-map')).toBeVisible()
})

test('address lookup resolves area information', async ({ page }) => {
  await page.goto('/')
  await waitForAppReady(page)
  const input = page.locator('#address-input')
  // TODO: Replace hard-coded Randers example addresses used in tests.
  await input.fill('Rådhustorvet 1, 8900 Randers C')
  await page.waitForTimeout(1000)
  await input.press('Enter')

  await expect(page.locator('#result-status')).toHaveText('Position fundet i spilleomraadet.', { timeout: 15000 })
  await expect(page.locator('#result-sogn')).toHaveText('Sankt Mortens')
  await expect(page.locator('#result-postnummer')).toHaveText('8900 Randers C')
  await expect(page.locator('#result-afstemning')).toHaveText('Fritidscentret', { timeout: 15000 })
})

test('browser geolocation resolves area information', async ({ page, context }, testInfo) => {
  await context.grantPermissions(['geolocation'], { origin: 'http://127.0.0.1:4173' })
  await context.setGeolocation({ longitude: 10.03639, latitude: 56.4607 })

  await page.goto('/')
  await waitForAppReady(page)
  await openMobilePanelIfNeeded(page, testInfo)
  await page.getByRole('button', { name: 'Brug min position' }).click()

  await expect(page.locator('#result-status')).toHaveText('Position fundet i spilleomraadet.', { timeout: 15000 })
  await expect(page.locator('#result-sogn')).toHaveText('Sankt Mortens')
  await expect(page.locator('#result-postnummer')).toHaveText('8900 Randers C')
  await expect(page.locator('#result-afstemning')).toHaveText('Fritidscentret', { timeout: 15000 })
})

test('desktop can click a stop and see its name', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'desktop', 'Only relevant in desktop mode')

  await page.goto('/')
  await waitForAppReady(page)

  const point = await page.evaluate(() => {
    const stopLayers = window.__appDebug?.stopLayer?.getLayers?.() || []
    const size = window.__appDebug?.map?.getSize?.()
    const mapRect = document.querySelector('#map')?.getBoundingClientRect()
    for (const candidate of stopLayers) {
      const child = candidate.getLayers ? candidate.getLayers()[0] : candidate
      const latlng = child.getLatLng()
      const containerPoint = window.__appDebug.map.latLngToContainerPoint(latlng)
      if (containerPoint.x > 420 && containerPoint.x < size.x - 80 && containerPoint.y > 80 && containerPoint.y < size.y - 80) {
        return { x: mapRect.left + containerPoint.x, y: mapRect.top + containerPoint.y }
      }
    }
    return null
  })

  if (!point) throw new Error('No stop point available for desktop click test')
  await page.mouse.click(point.x, point.y)
  await expect(page.locator('#result-status')).toContainText('Valgt stoppested')
})

test('phone can tap a stop and see its name', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'phone', 'Only relevant in phone mode')

  await page.goto('/')
  await waitForAppReady(page)

  const point = await page.evaluate(() => {
    const stopLayers = window.__appDebug?.stopLayer?.getLayers?.() || []
    const size = window.__appDebug?.map?.getSize?.()
    for (const candidate of stopLayers) {
      const child = candidate.getLayers ? candidate.getLayers()[0] : candidate
      const latlng = child.getLatLng()
      const containerPoint = window.__appDebug.map.latLngToContainerPoint(latlng)
      if (containerPoint.x > 40 && containerPoint.x < size.x - 40 && containerPoint.y > 60 && containerPoint.y < size.y - 260) {
        return { x: containerPoint.x, y: containerPoint.y }
      }
    }
    return null
  })

  if (!point) throw new Error('No stop point available for tap test')
  await page.touchscreen.tap(point.x, point.y)
  await expect(page.locator('#result-status')).toContainText('Valgt stoppested')
})
