/** On-device capture checks: blur and glare, measured in the browser before anything is uploaded.
 *  Runs on the participant's phone, so obvious retakes never cost a round trip or an OCR call. */

export interface CaptureCheck {
  blur: number
  glare: number
  warning: string | null
}

const BLUR_MIN = 40

export async function checkCapture(file: File): Promise<CaptureCheck> {
  const bitmap = await createImageBitmap(file)
  const width = 800
  const height = Math.max(1, Math.round((bitmap.height / bitmap.width) * width))
  const canvas = document.createElement('canvas')
  canvas.width = width
  canvas.height = height
  const context = canvas.getContext('2d', { willReadFrequently: true })
  if (!context) return { blur: BLUR_MIN, glare: 0, warning: null }
  context.drawImage(bitmap, 0, 0, width, height)
  bitmap.close()

  const { data } = context.getImageData(0, 0, width, height)
  const grey = new Float32Array(width * height)
  let blown = 0
  for (let i = 0, p = 0; i < data.length; i += 4, p++) {
    grey[p] = 0.299 * data[i] + 0.587 * data[i + 1] + 0.114 * data[i + 2]
    if (data[i] >= 250 && data[i + 1] >= 250 && data[i + 2] >= 250) blown++
  }

  // Variance of the Laplacian: low means soft focus.
  let sum = 0
  let sumSquares = 0
  let count = 0
  for (let y = 1; y < height - 1; y++) {
    for (let x = 1; x < width - 1; x++) {
      const i = y * width + x
      const value = 4 * grey[i] - grey[i - 1] - grey[i + 1] - grey[i - width] - grey[i + width]
      sum += value
      sumSquares += value * value
      count++
    }
  }
  const blur = sumSquares / count - (sum / count) ** 2
  const glare = blown / (width * height)
  // Only blur is warned about here. A bright card in bright light looks like "glare" to a whole-image
  // ratio, and a false retake is worse than a round trip, so glare is left to the server's blob check.
  return {
    blur,
    glare,
    warning: blur < BLUR_MIN ? 'This looks blurry. Hold the phone steady in good light and take it again.' : null,
  }
}
