// The app's own stylesheet (src/index.css), for tests of how something looks: with it in the
// document, jsdom's getComputedStyle reports what the stylesheet applies. jsdom does not
// resolve CSS variables, so the light theme's values (the first :root block) are filled in.
// vitest.config.ts lets this one CSS file be read as text.
import { onTestFinished } from 'vitest'
import css from '../index.css?raw'

export function useAppStylesheet() {
  const theme = new Map(
    [...(css.match(/:root\s*\{([^}]*)\}/)?.[1] ?? '').matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)].map((m) => [
      m[1],
      m[2].trim(),
    ]),
  )
  const style = document.createElement('style')
  style.textContent = css.replace(/var\((--[\w-]+)\)/g, (_, name: string) => theme.get(name) ?? 'initial')
  document.head.append(style)
  onTestFinished(() => style.remove())
}
