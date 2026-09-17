import { useEffect, useState } from 'react'
import { health } from './api/client'

// Stream E builds two surfaces here:
//   /capture  participant: on-device blur/glare/face guidance, upload, instant result with one-tap fixes
//   /console  organiser: review queue, case view with evidence ledger, copilot summary, approve/reject
export default function App() {
  const [api, setApi] = useState<string>('checking…')

  useEffect(() => {
    health()
      .then((h) => setApi(`API ${h.status} · v${h.version}`))
      .catch((error: Error) => setApi(error.message))
  }, [])

  return (
    <main className="mx-auto max-w-3xl px-4 py-12 font-sans text-slate-900">
      <h1 className="text-4xl font-bold tracking-tight">
        Pehchaan <span className="text-2xl font-medium text-slate-500">पहचान</span>
      </h1>
      <p className="mt-2 text-lg text-slate-600">Identity and eligibility verification for Hackingly registrations.</p>
      <p className="mt-6 inline-block rounded-full bg-slate-100 px-3 py-1 font-mono text-sm">{api}</p>
    </main>
  )
}
