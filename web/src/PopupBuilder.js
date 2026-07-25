function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;')
}

export function buildAdminPopup(properties, config) {
  const title = properties?.[config.popupTitleField] || config.fallbackTitle || 'Ukendt område'
  const lines = config.popupFields
    .map((field) => {
      const value = properties?.[field.key]
      if (value === null || value === undefined || value === '') return null
      return `<p><strong>${escapeHtml(field.label)}:</strong> ${escapeHtml(value)}</p>`
    })
    .filter(Boolean)

  return [
    '<article class="admin-popup">',
    `  <h2>${escapeHtml(title)}</h2>`,
    ...lines,
    '</article>',
  ].join('')
}

export function buildContextPopup(context) {
  const lines = []
  if (context.kommune) lines.push(`<p><strong>Kommune:</strong> ${escapeHtml(context.kommune)}</p>`)
  if (context.postomraade) lines.push(`<p><strong>Postområde:</strong> ${escapeHtml(context.postomraade)}</p>`)
  if (context.opstillingskreds) lines.push(`<p><strong>Opstillingskreds:</strong> ${escapeHtml(context.opstillingskreds)}</p>`)
  if (context.sogn) lines.push(`<p><strong>Sogn:</strong> ${escapeHtml(context.sogn)}</p>`)
  if (context.stationName) lines.push(`<p><strong>Station:</strong> ${escapeHtml(context.stationName)}</p>`)
  if (context.lines) lines.push(`<p><strong>Linjer:</strong> ${escapeHtml(context.lines)}</p>`)

  return [
    '<article class="admin-popup">',
    ...lines,
    '</article>',
  ].join('')
}
