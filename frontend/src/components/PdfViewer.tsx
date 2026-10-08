import { forwardRef, memo, useCallback, useEffect, useImperativeHandle, useLayoutEffect, useRef, useState } from 'react'
import { Document, Page, pdfjs } from 'react-pdf'
import 'react-pdf/dist/Page/AnnotationLayer.css'
import 'react-pdf/dist/Page/TextLayer.css'

// The worker must be the same PDF.js version that react-pdf bundles.
pdfjs.GlobalWorkerOptions.workerSrc = new URL('pdfjs-dist/build/pdf.worker.min.mjs', import.meta.url).toString()

export interface PdfViewerHandle {
  // Scroll so that `top` (0 = top of the page, 1 = bottom) of `page` is in view.
  scrollTo: (page: number, top?: number | null) => void
}

interface Props {
  url: string
  // Reading position as page + fraction of that page (e.g. 4.6 = 60% down page 4),
  // measured just below the top of the view; Infinity once scrolled to the end.
  onPositionChange?: (position: number) => void
}

const ZOOM_STEPS = [0.5, 0.75, 1, 1.25, 1.5, 2, 2.5, 3]
const GAP = 12 // px between pages; matches .pdf-page margin in index.css

const PdfViewer = forwardRef<PdfViewerHandle, Props>(function PdfViewer({ url, onPositionChange }, ref) {
  const scroller = useRef<HTMLDivElement>(null)
  const pageRefs = useRef<(HTMLDivElement | null)[]>([])
  const [numPages, setNumPages] = useState(0)
  const [fitWidth, setFitWidth] = useState(600)
  const [zoom, setZoom] = useState(1) // multiplier on the fit-to-width size
  const [ratio, setRatio] = useState(11 / 8.5) // page height / width, until the PDF says otherwise
  const [rendered, setRendered] = useState<Set<number>>(() => new Set([1, 2]))
  // Last measured size of pages that were unloaded, so pages of a different
  // size (e.g. a landscape table) keep their height and the scroll does not jump.
  const [measured, setMeasured] = useState<Map<number, { width: number; height: number }>>(() => new Map())
  const [current, setCurrent] = useState(1)
  const [error, setError] = useState<string | null>(null)

  const pageWidth = Math.max(200, Math.round(fitWidth * zoom))
  const pageHeight = Math.round(pageWidth * ratio)
  // Reading position to restore after the page size changes (zoom, resize).
  const anchor = useRef<number | null>(null)

  // Page offsets are relative to the scroller (.pdf-scroll is position: relative).
  const positionAt = useCallback(
    (y: number): number => {
      let index = 0
      pageRefs.current.slice(0, numPages).forEach((el, i) => {
        if (el && el.offsetTop <= y) index = i
      })
      const el = pageRefs.current[index]
      if (!el) return 1
      return index + 1 + Math.min(1, Math.max(0, (y - el.offsetTop) / el.clientHeight))
    },
    [numPages],
  )

  const scrollToPosition = useCallback((position: number, behavior: ScrollBehavior) => {
    const root = scroller.current
    const page = Math.floor(position)
    const el = pageRefs.current[page - 1]
    if (!root || !el) return
    root.scrollTo({ top: Math.max(0, el.offsetTop + (position - page) * el.clientHeight - 16), behavior })
  }, [])

  // Fit pages to the panel's width, following resizes, and keep the place.
  useEffect(() => {
    const el = scroller.current
    if (!el) return
    const observer = new ResizeObserver(() => {
      const width = Math.max(200, el.clientWidth - 2 * GAP)
      setFitWidth((prev) => {
        if (prev !== width && anchor.current === null) anchor.current = positionAt(el.scrollTop + 16)
        return width
      })
    })
    observer.observe(el)
    return () => observer.disconnect()
  }, [positionAt])

  function zoomTo(next: number) {
    const el = scroller.current
    if (el) anchor.current = positionAt(el.scrollTop + 16)
    setZoom(next)
  }

  // Render only pages near the viewport, and drop pages that move away, so long
  // papers stay fast and memory stays bounded.
  useEffect(() => {
    const root = scroller.current
    if (!root || numPages === 0) return
    const near = new Set<number>()
    const observer = new IntersectionObserver(
      (entries) => {
        const left: [number, { width: number; height: number }][] = []
        for (const e of entries) {
          const el = e.target as HTMLElement
          const page = Number(el.dataset.page)
          if (e.isIntersecting) near.add(page)
          else if (near.delete(page)) left.push([page, { width: el.offsetWidth, height: el.offsetHeight }])
        }
        setRendered((prev) => (prev.size === near.size && [...near].every((p) => prev.has(p)) ? prev : new Set(near)))
        if (left.length) setMeasured((prev) => new Map([...prev, ...left]))
      },
      { root, rootMargin: '150% 0px' },
    )
    pageRefs.current.slice(0, numPages).forEach((el) => el && observer.observe(el))
    return () => observer.disconnect()
  }, [numPages])

  // Track the page shown in the toolbar (at a third of the view's height) and
  // the reading position just below the top of the view (for the outline).
  const lastPosition = useRef<number | null>(null)
  const update = useCallback(() => {
    const root = scroller.current
    if (!root || numPages === 0) return
    const page = Math.floor(positionAt(root.scrollTop + root.clientHeight * 0.3))
    setCurrent((prev) => (prev === page ? prev : page))
    const atEnd = root.scrollTop + root.clientHeight >= root.scrollHeight - 4
    // 24px: just below where a section jump puts its heading (16px from the top),
    // so the jumped-to section counts as the one being read.
    const position = atEnd ? Number.POSITIVE_INFINITY : Math.round(positionAt(root.scrollTop + 24) * 1000) / 1000
    if (position !== lastPosition.current) {
      lastPosition.current = position
      onPositionChange?.(position)
    }
  }, [numPages, onPositionChange, positionAt])

  // At most one update per animation frame while scrolling.
  const frame = useRef<number | null>(null)
  const onScroll = useCallback(() => {
    if (frame.current !== null) return
    frame.current = requestAnimationFrame(() => {
      frame.current = null
      update()
    })
  }, [update])
  useEffect(() => () => {
    if (frame.current !== null) cancelAnimationFrame(frame.current)
  }, [])

  // After a zoom or resize, return to the stored reading position.
  useLayoutEffect(() => {
    if (anchor.current === null) return
    scrollToPosition(anchor.current, 'auto')
    anchor.current = null
    update()
  }, [pageWidth, scrollToPosition, update])

  useImperativeHandle(
    ref,
    () => ({
      scrollTo(page, top) {
        scrollToPosition(page + Math.min(Math.max(top ?? 0, 0), 0.999), 'smooth')
      },
    }),
    [scrollToPosition],
  )

  const zoomIndex = ZOOM_STEPS.indexOf(zoom)
  return (
    <div className="pdf-viewer">
      <div className="pdf-toolbar">
        <button className="btn small" onClick={() => zoomTo(ZOOM_STEPS[zoomIndex - 1])} disabled={zoomIndex <= 0} aria-label="Zoom out">
          −
        </button>
        <span className="muted">{Math.round(zoom * 100)}%</span>
        <button
          className="btn small"
          onClick={() => zoomTo(ZOOM_STEPS[zoomIndex + 1])}
          disabled={zoomIndex >= ZOOM_STEPS.length - 1}
          aria-label="Zoom in"
        >
          +
        </button>
        <button className="btn small" onClick={() => zoomTo(1)} disabled={zoom === 1}>
          Fit width
        </button>
        <span className="muted pdf-pages">{numPages ? `Page ${current} of ${numPages}` : ''}</span>
        <a className="btn small" href={url} target="_blank" rel="noreferrer">
          Open PDF ↗
        </a>
      </div>
      <div className="pdf-scroll" ref={scroller} onScroll={onScroll}>
        {error ? (
          <div className="alert error">{error}</div>
        ) : (
          <Document
            // Without suspense, loading and errors stay inside this component
            // (react-pdf's default would suspend to the page-level fallback,
            // hiding the whole viewer whenever a page loads, and a load error
            // would unmount the app).
            suspense={false}
            file={url}
            loading={<p className="muted pdf-message">Loading PDF…</p>}
            onLoadSuccess={async (pdf) => {
              setError(null)
              setNumPages(pdf.numPages)
              const first = await pdf.getPage(1)
              const viewport = first.getViewport({ scale: 1 })
              setRatio(viewport.height / viewport.width)
            }}
            onLoadError={() => setError('The PDF could not be displayed.')}
            onItemClick={({ pageNumber }) => scrollToPosition(pageNumber, 'smooth')}
            externalLinkTarget="_blank"
            externalLinkRel="noreferrer"
          >
            {Array.from({ length: numPages }, (_, i) => (
              <div
                key={i}
                className="pdf-page"
                data-page={i + 1}
                ref={(el) => {
                  pageRefs.current[i] = el
                }}
                style={{
                  width: pageWidth,
                  minHeight: measured.get(i + 1)?.width === pageWidth ? measured.get(i + 1)?.height : pageHeight,
                }}
              >
                {rendered.has(i + 1) && (
                  <Page
                    suspense={false}
                    pageNumber={i + 1}
                    width={pageWidth}
                    loading={<div style={{ height: pageHeight }} />}
                    error={<p className="muted pdf-message">This page could not be displayed.</p>}
                  />
                )}
              </div>
            ))}
          </Document>
        )}
      </div>
    </div>
  )
})

// Memoized: the reader re-renders as the reading position changes, and the
// viewer's props (url, callback) stay the same.
export default memo(PdfViewer)
