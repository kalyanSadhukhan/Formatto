import { describe, it, expect } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { UnresolvedMappingsList, DiagnosticsList } from './App'
import { ErrorBoundary } from './ErrorBoundary'

describe('UnresolvedMappingsList Regression Tests', () => {
  it('renders unresolved mapping objects with {element_id, type, preview} without crashing', () => {
    const diagnosticEntries = [
      {
        element_id: 'element_123',
        type: 'paragraph',
        preview: 'Example unresolved content',
      },
      {
        element_id: 'el_65587154_0094',
        type: 'paragraph',
        preview: 'Student Consent Form',
      },
    ]

    // Pre-fix: Threw "Objects are not valid as a React child (found: object with keys {element_id, type, preview})"
    let html = ''
    expect(() => {
      html = renderToStaticMarkup(<UnresolvedMappingsList items={diagnosticEntries} />)
    }).not.toThrow()

    // Assert that properties are rendered explicitly
    expect(html).toContain('element_123')
    expect(html).toContain('paragraph')
    expect(html).toContain('Example unresolved content')
    expect(html).toContain('el_65587154_0094')
    expect(html).toContain('Student Consent Form')
    expect(html).toContain('Unresolved Mappings (2)')
  })

  it('renders realistic large payload matching backend job execution (e.g. 93 elements)', () => {
    const realPayload = Array.from({ length: 93 }, (_, i) => ({
      element_id: `el_65587154_${String(i).padStart(4, '0')}`,
      type: i % 3 === 0 ? 'heading_2' : i % 3 === 1 ? 'paragraph' : 'list_item',
      preview: `Preview of document unmapped source snippet #${i + 1}`,
    }))

    let html = ''
    expect(() => {
      html = renderToStaticMarkup(<UnresolvedMappingsList items={realPayload} />)
    }).not.toThrow()

    expect(html).toContain('Unresolved Mappings (93)')
    expect(html).toContain('el_65587154_0000')
    expect(html).toContain('el_65587154_0092')
    expect(html).toContain('Preview of document unmapped source snippet #1')
  })

  it('safely handles missing, partial, null, and unexpected properties', () => {
    const mixedEntries = [
      { element_id: 'only_id' },
      { type: 'heading_1' },
      { preview: 'only preview text' },
      {},
      null,
      undefined,
      'Legacy raw string element',
    ]

    let html = ''
    expect(() => {
      html = renderToStaticMarkup(<UnresolvedMappingsList items={mixedEntries} />)
    }).not.toThrow()

    expect(html).toContain('only_id')
    expect(html).toContain('heading_1')
    expect(html).toContain('only preview text')
    expect(html).toContain('Legacy raw string element')
  })

  it('returns null on empty, null, or non-array inputs', () => {
    expect(renderToStaticMarkup(<UnresolvedMappingsList items={[]} />)).toBe('')
    expect(renderToStaticMarkup(<UnresolvedMappingsList items={null} />)).toBe('')
    expect(renderToStaticMarkup(<UnresolvedMappingsList items={undefined} />)).toBe('')
  })
})

describe('DiagnosticsList Tests', () => {
  it('safely renders diagnostic logs whether strings or objects', () => {
    const diagnostics = [
      'Preserved all 9 document sections.',
      { message: 'Structured diagnostic entry with message' },
      { stage: 'docx_generation', status: 'verified' },
      null,
    ]

    let html = ''
    expect(() => {
      html = renderToStaticMarkup(<DiagnosticsList diagnostics={diagnostics} />)
    }).not.toThrow()

    expect(html).toContain('Preserved all 9 document sections.')
    expect(html).toContain('Structured diagnostic entry with message')
    expect(html).toContain('stage: docx_generation')
  })
})

describe('ErrorBoundary Tests', () => {
  it('renders children when no error occurs', () => {
    const html = renderToStaticMarkup(
      <ErrorBoundary fallbackTitle="Fallback">
        <div>Safe Content</div>
      </ErrorBoundary>,
    )
    expect(html).toContain('Safe Content')
  })
})
