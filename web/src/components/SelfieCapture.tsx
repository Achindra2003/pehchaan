import { useEffect, useRef, useState } from 'react'

/** A selfie may only be called "camera" if we actually took it here. A file chosen from the gallery is an
 *  upload, whatever it looks like, and the server refuses to count an upload as proof of presence. */
export default function SelfieCapture({
  onCapture,
}: {
  onCapture: (file: File | null, source: 'camera' | 'upload') => void
}) {
  const [streaming, setStreaming] = useState(false)
  const [taken, setTaken] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const video = useRef<HTMLVideoElement>(null)
  const stream = useRef<MediaStream | null>(null)

  useEffect(() => () => stop(), [])

  function stop() {
    stream.current?.getTracks().forEach((track) => track.stop())
    stream.current = null
    setStreaming(false)
  }

  async function start() {
    setError(null)
    try {
      const media = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'user' } })
      stream.current = media
      setStreaming(true)
      if (video.current) {
        video.current.srcObject = media
        await video.current.play()
      }
    } catch {
      setError('No camera available here. You can attach a photo instead; it counts for less.')
    }
  }

  function take() {
    const element = video.current
    if (!element) return
    const canvas = document.createElement('canvas')
    canvas.width = element.videoWidth
    canvas.height = element.videoHeight
    canvas.getContext('2d')?.drawImage(element, 0, 0)
    canvas.toBlob((blob) => {
      if (!blob) return
      setTaken(URL.createObjectURL(blob))
      onCapture(new File([blob], 'selfie.jpg', { type: 'image/jpeg' }), 'camera')
      stop()
    }, 'image/jpeg', 0.92)
  }

  return (
    <div className="space-y-2">
      <span className="block text-sm font-medium text-muted">Selfie (optional)</span>

      {taken ? (
        <div className="flex items-center gap-3">
          <img src={taken} alt="Your selfie" className="h-20 w-20 rounded-lg object-cover" />
          <button
            type="button"
            className="text-sm text-accent underline"
            onClick={() => {
              setTaken(null)
              onCapture(null, 'camera')
            }}
          >
            Take it again
          </button>
        </div>
      ) : streaming ? (
        <div className="space-y-2">
          <video ref={video} className="w-full max-w-xs rounded-lg bg-black" playsInline muted />
          <div className="flex gap-2">
            <button type="button" onClick={take} className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white">
              Take the photo
            </button>
            <button type="button" onClick={stop} className="rounded-lg border border-rule px-4 py-2 text-sm">
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <div className="flex flex-wrap items-center gap-3">
          <button type="button" onClick={start} className="rounded-lg border border-accent px-4 py-2 text-sm text-accent">
            Use the camera
          </button>
          <label className="text-sm text-muted">
            or{' '}
            <input
              type="file"
              accept="image/*"
              className="w-40 text-sm"
              onChange={(e) => onCapture(e.target.files?.[0] ?? null, 'upload')}
            />
          </label>
        </div>
      )}
      {error && <p className="text-sm text-warn">{error}</p>}
    </div>
  )
}
