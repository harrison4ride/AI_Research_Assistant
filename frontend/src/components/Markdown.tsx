import ReactMarkdown, { type Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'

// Module scope: a new object per render would make ReactMarkdown re-render the
// whole tree on every streamed text delta.
const PLUGINS = [remarkGfm]
// A link whose URL carries a query string could smuggle data out on a click, so
// show it as text with the full URL visible instead of making it clickable.
function carriesData(href: string | undefined): boolean {
  if (!href) return false
  try {
    return new URL(href, window.location.href).search !== ''
  } catch {
    return true
  }
}

const COMPONENTS: Components = {
  // `node` is react-markdown's syntax-tree object; don't pass it to the DOM.
  a: ({ node: _node, href, children, ...props }) =>
    carriesData(href) ? (
      <span>
        {children} <code>{href}</code>
      </span>
    ) : (
      <a {...props} href={href} title={href} target="_blank" rel="noreferrer">
        {children}
      </a>
    ),
  // Never load images from model output: an image URL could carry data out
  // (for example, text the model was tricked into writing by a malicious PDF).
  img: ({ alt }) => <span className="muted">[image{alt ? `: ${alt}` : ''}]</span>,
}

// Renders LLM output. react-markdown ignores raw HTML, so model text can't inject markup.
export default function Markdown({ children }: { children: string }) {
  return (
    <div className="markdown">
      <ReactMarkdown remarkPlugins={PLUGINS} components={COMPONENTS}>
        {children}
      </ReactMarkdown>
    </div>
  )
}
