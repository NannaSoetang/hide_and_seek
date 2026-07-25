import './style.css'
import { WhereAmIPage } from './WhereAmIPage.js'

async function init() {
  const page = new WhereAmIPage()
  await page.init()
  document.body.dataset.pageReady = 'true'
}

init().catch((error) => {
  console.error('Kunne ikke starte Hvor er jeg?-siden.', error)
})
