import ReactMarkdown, { type Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'

// Module scope: a new object per render would make ReactMarkdown re-render the
// whole tree on every streamed text delta.
const PLUGINS = [remarkGfm]
const COMPONENTS: Components = {
  // `node` is react-markdown's syntax-tree object; don't pass it to the DOM.
  a: ({ node: _node, ...props }) => <a {...props} target="_blank" rel="noreferrer" />,
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
