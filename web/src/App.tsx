import { useState } from 'react'
import Console from './components/Console'
import Verify from './components/Verify'

export default function App() {
  const [view, setView] = useState<'verify' | 'console'>(
    window.location.hash === '#console' ? 'console' : 'verify',
  )

  function go(next: 'verify' | 'console') {
    setView(next)
    window.location.hash = next === 'console' ? '#console' : ''
  }

  return (
    <div className="mx-auto max-w-6xl px-4 py-6 md:py-10">
      <header className="mb-6 flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight md:text-3xl">
            Pehchaan <span className="font-dev text-xl text-muted">पहचान</span>
          </h1>
          <p className="text-sm text-muted">Identity and eligibility verification for Hackingly registrations</p>
        </div>
        <nav className="flex rounded-lg border border-rule bg-sheet p-1">
          {(['verify', 'console'] as const).map((tab) => (
            <button
              key={tab}
              onClick={() => go(tab)}
              className={`rounded-md px-4 py-2 text-sm font-medium ${
                view === tab ? 'bg-accent text-white' : 'text-muted'
              }`}
            >
              {tab === 'verify' ? 'Participant' : 'Organiser'}
            </button>
          ))}
        </nav>
      </header>
      {view === 'verify' ? <Verify /> : <Console />}
    </div>
  )
}
