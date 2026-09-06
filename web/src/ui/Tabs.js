export class Tabs {
  constructor(entries, { onShow } = {}) {
    this.entries = entries
    this.onShow = onShow
  }

  bind() {
    for (const [index, entry] of this.entries.entries()) {
      const isActive = entry.tab.getAttribute('aria-selected') === 'true'
      entry.tab.tabIndex = isActive ? 0 : -1
      entry.panel.hidden = !isActive
      entry.tab.addEventListener('click', () => this.show(entry.id))
      entry.tab.addEventListener('keydown', (event) => this.handleKeydown(event, index))
    }
  }

  handleKeydown(event, currentIndex) {
    const lastIndex = this.entries.length - 1
    const targetIndex = {
      ArrowLeft: currentIndex === 0 ? lastIndex : currentIndex - 1,
      ArrowRight: currentIndex === lastIndex ? 0 : currentIndex + 1,
      Home: 0,
      End: lastIndex,
    }[event.key]

    if (targetIndex === undefined) return
    event.preventDefault()
    const target = this.entries[targetIndex]
    this.show(target.id)
    setTimeout(() => target.tab.focus(), 0)
  }

  show(activeId) {
    for (const entry of this.entries) {
      const isActive = entry.id === activeId
      entry.tab.classList.toggle('is-active', isActive)
      entry.tab.setAttribute('aria-selected', String(isActive))
      entry.tab.tabIndex = isActive ? 0 : -1
      entry.panel.classList.toggle('is-hidden', !isActive)
      entry.panel.hidden = !isActive
    }
    this.onShow?.(activeId)
  }
}