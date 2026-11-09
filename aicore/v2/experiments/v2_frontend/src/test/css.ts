export function extractCssAtRuleBlock(css: string, marker: string): string {
  const markerStart = css.indexOf(marker)
  if (markerStart < 0) return ''

  const openingBrace = css.indexOf('{', markerStart + marker.length)
  if (openingBrace < 0) return ''

  let depth = 0
  for (let index = openingBrace; index < css.length; index += 1) {
    if (css[index] === '{') {
      depth += 1
    } else if (css[index] === '}') {
      depth -= 1
      if (depth === 0) return css.slice(markerStart, index + 1)
    }
  }

  return ''
}
