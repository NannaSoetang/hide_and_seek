import './style.css'
import { GuidePage } from './GuidePage.js'

async function init() {
  const page = new GuidePage()
  await page.init()
  document.body.dataset.guideReady = 'true'
}

init().catch((error) => {
  console.error('Kunne ikke starte Spilguide.', error)
})
