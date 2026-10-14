import '@testing-library/jest-dom/vitest'

// React Flow (the mind map) needs these browser APIs, which jsdom lacks.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??= ResizeObserverStub as unknown as typeof ResizeObserver
globalThis.DOMMatrixReadOnly ??= class {
  m22 = 1
  constructor(public transform?: string) {}
} as unknown as typeof DOMMatrixReadOnly
