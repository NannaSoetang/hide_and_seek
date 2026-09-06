import test from 'node:test'
import assert from 'node:assert/strict'

import { ADMIN_LAYERS, TRANSIT_NETWORKS, getAdminLayerLabel } from './theme.js'

test('admin layer config is the canonical source for layer metadata', () => {
  assert.deepEqual(
    ADMIN_LAYERS.map((layer) => layer.id),
    ['kommuner', 'opstillingskredse', 'postomraader', 'sogne'],
  )
  assert.equal(getAdminLayerLabel('kommuner', 'en'), 'Municipalities')
  assert.equal(getAdminLayerLabel('opstillingskredse', 'en'), 'Constituencies')
  assert.equal(getAdminLayerLabel('postomraader', 'en'), 'Postal areas')
  assert.equal(getAdminLayerLabel('sogne', 'en'), 'Parishes')
})

test('transit networks are derived from the canonical config instead of duplicated literals', () => {
  assert.deepEqual(TRANSIT_NETWORKS, ['metro', 's-tog', 'bus'])
})
