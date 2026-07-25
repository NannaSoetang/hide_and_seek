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

test('interactive map loads title, links, and map container', async ({ page }) => {
  await page.goto('/')
  await waitForMapReady(page)

  await expect(page.getByRole('heading', { name: 'København Metro og S-tog' })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Hvor er jeg?' })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Spilguide' })).toBeVisible()
  await expect(page.locator('#map')).toBeVisible()
})

test('interactive map can open station context popup', async ({ page }) => {
  await page.goto('/')
  await waitForMapReady(page)

  await page.evaluate(() => {
    const stationLayer = window.__appDebug?.metroLayers?.stationLayer
    const firstStation = stationLayer?.getLayers?.()?.[0]
    if (!firstStation) throw new Error('No metro station layer available')
    firstStation.fire('click')
  })

  await expect(page.locator('.leaflet-popup-content')).toContainText('Station:')
})

test('print page loads map and generated route legend', async ({ page }) => {
  await page.goto('/print.html')

  await expect(page.getByRole('heading', { name: 'Hide & Seek København - Print' })).toBeVisible()
  await expect(page.locator('#print-map')).toBeVisible()
  await expect(page.locator('.legend-footer')).toBeVisible()
  await expect(page.getByText('Metro')).toBeVisible()
  await expect(page.getByText('S-tog')).toBeVisible()
})

test('where-am-i page loads and tabs can switch', async ({ page }) => {
  await page.goto('/where-am-i.html')
  await waitForWhereReady(page)

  await expect(page.getByRole('heading', { name: 'Hvor er jeg?' })).toBeVisible()
  await expect(page.locator('#panel-location')).toBeVisible()

  await page.getByRole('tab', { name: 'Adresse' }).click()
  await expect(page.locator('#panel-address')).toBeVisible()
  await expect(page.locator('#panel-location')).toHaveClass(/is-hidden/)
})

test('guide page loads station groups and tabs', async ({ page }) => {
  await page.goto('/guide.html')
  await waitForGuideReady(page)

  await expect(page.getByRole('heading', { name: 'Spilguide' })).toBeVisible()
  await expect(page.locator('#station-groups .guide-line-accordion').first()).toBeVisible()

  await page.getByRole('tab', { name: 'Spilleregler' }).click()
  await expect(page.locator('#guide-panel-rules')).toBeVisible()
})
