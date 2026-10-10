export const DEFAULT_LOCALE = 'da'
const LOCALE_STORAGE_KEY = 'hide-and-seek-locale'

export function getLocale() {
  return localStorage.getItem(LOCALE_STORAGE_KEY) === 'en' ? 'en' : DEFAULT_LOCALE
}

export function setLocale(locale) {
  const nextLocale = locale === 'en' ? 'en' : DEFAULT_LOCALE
  localStorage.setItem(LOCALE_STORAGE_KEY, nextLocale)
  document.documentElement.lang = nextLocale
  document.dispatchEvent(new CustomEvent('localechange', { detail: { locale: nextLocale } }))
}

export function bindLanguageControls() {
  const buttons = [...document.querySelectorAll('[data-language]')]
  const update = () => {
    const locale = getLocale()
    for (const button of buttons) {
      button.setAttribute('aria-pressed', String(button.dataset.language === locale))
    }
  }

  for (const button of buttons) {
    button.addEventListener('click', () => setLocale(button.dataset.language))
  }
  document.addEventListener('localechange', update)
  update()
}

export function translateStaticContent(content) {
  for (const element of document.querySelectorAll('[data-i18n]')) {
    const value = element.dataset.i18n.split('.').reduce((object, key) => object?.[key], content)
    if (value !== undefined) element.textContent = value
  }
  for (const element of document.querySelectorAll('[data-i18n-placeholder]')) {
    const value = element.dataset.i18nPlaceholder.split('.').reduce((object, key) => object?.[key], content)
    if (value !== undefined) element.setAttribute('placeholder', value)
  }
  for (const element of document.querySelectorAll('[data-i18n-aria-label]')) {
    const value = element.dataset.i18nAriaLabel.split('.').reduce((object, key) => object?.[key], content)
    if (value !== undefined) element.setAttribute('aria-label', value)
  }
}