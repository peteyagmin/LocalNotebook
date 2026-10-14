import { useState } from 'react'
import type { Citation, FlashcardsData } from '../api'
import { SourceChips } from './SourceChips'

interface FlashcardsViewProps {
  data: FlashcardsData
  citations: Citation[]
  onOpenCitation: (citation: Citation) => void
}

const buttonClass =
  'rounded border border-neutral-300 px-3 py-1 text-sm hover:bg-neutral-100 disabled:opacity-50 dark:border-neutral-700 dark:hover:bg-neutral-800'

export function FlashcardsView(props: FlashcardsViewProps) {
  const [tab, setTab] = useState<'cards' | 'quiz'>('cards')
  const tabClass = (active: boolean) =>
    `rounded-t px-4 py-1.5 text-sm ${active ? 'border-b-2 border-blue-600 font-semibold' : 'text-neutral-500'}`
  return (
    <div className="space-y-4">
      <div
        role="tablist"
        className="flex gap-2 border-b border-neutral-200 dark:border-neutral-800"
      >
        <button
          role="tab"
          type="button"
          aria-selected={tab === 'cards'}
          className={tabClass(tab === 'cards')}
          onClick={() => setTab('cards')}
        >
          Flashcards
        </button>
        <button
          role="tab"
          type="button"
          aria-selected={tab === 'quiz'}
          className={tabClass(tab === 'quiz')}
          onClick={() => setTab('quiz')}
        >
          Quiz
        </button>
      </div>
      {tab === 'cards' ? <Cards {...props} /> : <Quiz {...props} />}
    </div>
  )
}

function Cards({ data, citations, onOpenCitation }: FlashcardsViewProps) {
  const [index, setIndex] = useState(0)
  const [flipped, setFlipped] = useState(false)
  const cards = data.flashcards
  if (cards.length === 0) return <p className="text-neutral-500">No flashcards.</p>
  const card = cards[index]
  const go = (next: number) => {
    setIndex(next)
    setFlipped(false)
  }
  return (
    <div
      className="space-y-3"
      onKeyDown={(e) => {
        if (e.key === 'ArrowRight' && index < cards.length - 1) go(index + 1)
        if (e.key === 'ArrowLeft' && index > 0) go(index - 1)
      }}
    >
      <div className="[perspective:1000px]">
        <div
          data-testid="card"
          data-flipped={flipped}
          className="relative h-56 transition-transform duration-500 [transform-style:preserve-3d] motion-reduce:transition-none"
          style={{ transform: flipped ? 'rotateY(180deg)' : 'none' }}
        >
          <button
            type="button"
            aria-label={`Flashcard front: ${card.front}. Press to flip.`}
            aria-hidden={flipped}
            tabIndex={flipped ? -1 : 0}
            onClick={() => setFlipped(true)}
            className="absolute inset-0 flex items-center justify-center rounded-lg border border-neutral-300 bg-white p-6 text-center text-lg [backface-visibility:hidden] dark:border-neutral-700 dark:bg-neutral-900"
          >
            {card.front}
          </button>
          <div
            aria-hidden={!flipped}
            className="absolute inset-0 flex flex-col items-center justify-center gap-2 rounded-lg border border-blue-300 bg-blue-50 p-6 text-center text-lg [backface-visibility:hidden] [transform:rotateY(180deg)] dark:border-blue-800 dark:bg-blue-950"
          >
            <button
              type="button"
              tabIndex={flipped ? 0 : -1}
              aria-label={`Flashcard back: ${card.back}. Press to flip back.`}
              onClick={() => setFlipped(false)}
              className="w-full flex-1"
            >
              {card.back}
            </button>
            <div>
              <SourceChips labels={card.sources} citations={citations} onOpen={onOpenCitation} />
            </div>
          </div>
        </div>
      </div>
      <div className="flex items-center justify-between">
        <button
          type="button"
          className={buttonClass}
          disabled={index === 0}
          onClick={() => go(index - 1)}
        >
          Previous card
        </button>
        <span aria-live="polite">
          Card {index + 1} of {cards.length}
        </span>
        <button
          type="button"
          className={buttonClass}
          disabled={index === cards.length - 1}
          onClick={() => go(index + 1)}
        >
          Next card
        </button>
      </div>
    </div>
  )
}

function Quiz({ data, citations, onOpenCitation }: FlashcardsViewProps) {
  const questions = data.quiz
  const [index, setIndex] = useState(0)
  const [answers, setAnswers] = useState<number[]>([])
  const [picked, setPicked] = useState<number | null>(null)
  if (questions.length === 0) return <p className="text-neutral-500">No quiz questions.</p>

  if (index >= questions.length) {
    const score = answers.filter((a, i) => a === questions[i].correct_index).length
    return (
      <div className="space-y-3 text-center">
        <p role="status" className="text-2xl font-semibold">
          You scored {score} of {questions.length}
        </p>
        <button
          type="button"
          className={buttonClass}
          onClick={() => {
            setIndex(0)
            setAnswers([])
            setPicked(null)
          }}
        >
          Retake quiz
        </button>
      </div>
    )
  }

  const q = questions[index]
  const answered = picked !== null
  return (
    <div className="space-y-3">
      <p className="text-xs text-neutral-500">
        Question {index + 1} of {questions.length}
      </p>
      <h3 className="text-lg font-semibold">{q.question}</h3>
      <div role="radiogroup" aria-label="Answers" className="space-y-2">
        {q.options.map((option, i) => {
          const correct = i === q.correct_index
          const state = !answered
            ? 'border-neutral-300 hover:bg-neutral-100 dark:border-neutral-700 dark:hover:bg-neutral-800'
            : correct
              ? 'border-green-600 bg-green-50 dark:bg-green-950'
              : i === picked
                ? 'border-red-600 bg-red-50 dark:bg-red-950'
                : 'border-neutral-200 opacity-60 dark:border-neutral-800'
          return (
            <button
              key={i}
              type="button"
              role="radio"
              aria-checked={picked === i}
              disabled={answered}
              onClick={() => setPicked(i)}
              className={`block w-full rounded border px-3 py-2 text-left ${state}`}
            >
              {option}
              {answered && correct && (
                <span className="ml-2 text-xs text-green-700">Correct answer</span>
              )}
              {answered && !correct && i === picked && (
                <span className="ml-2 text-xs text-red-700">Your answer</span>
              )}
            </button>
          )
        })}
      </div>
      {answered && (
        <div role="status" className="space-y-2 rounded bg-neutral-100 p-3 dark:bg-neutral-900">
          <p className="font-semibold">{picked === q.correct_index ? 'Correct!' : 'Not quite.'}</p>
          <p>
            {q.explanation}
            <SourceChips labels={q.sources} citations={citations} onOpen={onOpenCitation} />
          </p>
          <button
            type="button"
            className={buttonClass}
            onClick={() => {
              setAnswers([...answers, picked])
              setPicked(null)
              setIndex(index + 1)
            }}
          >
            {index === questions.length - 1 ? 'See score' : 'Next question'}
          </button>
        </div>
      )}
    </div>
  )
}
