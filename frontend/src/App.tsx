import { useCallback, useEffect, useRef, useState } from 'react'
import './App.css'

const apiBase = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '')

type Variant = {
  variant_key: string
  label: string
  status: string
  video_url: string | null
  error: string | null
  mock_fallback?: boolean
}

type JobResponse = {
  id: string
  scenario: string
  status: string
  demo_mode: boolean
  variants: Variant[]
  recommendation: string | null
  recommended_label: string | null
  error: string | null
}

async function postJob(scenario: string): Promise<{ job_id: string; demo_mode: boolean }> {
  const r = await fetch(`${apiBase}/api/jobs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ scenario }),
  })
  if (!r.ok) {
    const t = await r.text()
    throw new Error(t || `Failed to start job (${r.status})`)
  }
  return r.json()
}

async function getJob(id: string): Promise<JobResponse> {
  const r = await fetch(`${apiBase}/api/jobs/${id}`)
  if (!r.ok) {
    const t = await r.text()
    throw new Error(t || `Job not found (${r.status})`)
  }
  return r.json()
}

function variantDotClass(status: string): string {
  if (status === 'ok') return 'ok'
  if (status === 'failed') return 'fail'
  return 'running'
}

export default function App() {
  const [scenario, setScenario] = useState('')
  const [jobId, setJobId] = useState<string | null>(null)
  const [job, setJob] = useState<JobResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [samples, setSamples] = useState<string[]>([])
  const pollRef = useRef<number | null>(null)

  useEffect(() => {
    fetch(`${apiBase}/api/demo-scenarios`)
      .then((r) => r.json())
      .then((d) => setSamples(d.scenarios || []))
      .catch(() => setSamples([]))
  }, [])

  const stopPoll = useCallback(() => {
    if (pollRef.current) {
      window.clearInterval(pollRef.current)
      pollRef.current = null
    }
  }, [])

  useEffect(() => () => stopPoll(), [stopPoll])

  const pollJob = useCallback(
    (id: string) => {
      stopPoll()
      pollRef.current = window.setInterval(async () => {
        try {
          const j = await getJob(id)
          setJob(j)
          if (j.status === 'completed' || j.status === 'failed') {
            stopPoll()
            setLoading(false)
          }
        } catch (e) {
          setError(e instanceof Error ? e.message : 'Poll failed')
          stopPoll()
          setLoading(false)
        }
      }, 1500)
    },
    [stopPoll],
  )

  const onGenerate = async () => {
    setError(null)
    setJob(null)
    setJobId(null)
    setLoading(true)
    try {
      const { job_id } = await postJob(scenario)
      setJobId(job_id)
      const first = await getJob(job_id)
      setJob(first)
      pollJob(job_id)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Request failed')
      setLoading(false)
    }
  }

  const showResults = job && (job.status === 'completed' || job.status === 'failed')

  return (
    <div className="page">
      <header className="hero">
        <h1>ScenarioSim</h1>
        <p>
          Describe a real-world situation. We generate multiple short outcome simulations, compare them, and
          suggest which trajectory is strongest for your goals.
        </p>
        <div className="badge-row">
          {job?.demo_mode ? (
            <span className="badge">Demo mode · sample video URLs</span>
          ) : (
            <span className="badge muted">Live mode · BytePlus Seedance</span>
          )}
          {jobId ? (
            <span className="badge muted">
              Job <code style={{ fontSize: '0.85em' }}>{jobId.slice(0, 8)}…</code>
            </span>
          ) : null}
        </div>
      </header>

      <section className="panel">
        <label htmlFor="scenario">Scenario</label>
        <textarea
          id="scenario"
          value={scenario}
          onChange={(e) => setScenario(e.target.value)}
          placeholder="e.g. Our team must decide whether to delay launch to fix a performance regression discovered 48 hours before the keynote."
        />
        <div className="row">
          <button type="button" className="primary" disabled={loading || scenario.trim().length < 3} onClick={onGenerate}>
            {loading ? 'Generating…' : 'Generate outcomes'}
          </button>
          {loading ? (
            <span className="status">
              Status: <strong>{job?.status ?? 'starting'}</strong>
            </span>
          ) : null}
        </div>

        {samples.length > 0 ? (
          <div className="samples">
            <span>Try a sample scenario</span>
            <div className="sample-chips">
              {samples.map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => {
                    setScenario(s)
                    setError(null)
                  }}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        ) : null}

        {job && job.status === 'running' && job.variants.length > 0 ? (
          <ul className="progress-list">
            {job.variants.map((v) => (
              <li key={v.variant_key}>
                <span className={`dot ${variantDotClass(v.status)}`} />
                <span>
                  {v.label}: <strong>{v.status}</strong>
                  {v.mock_fallback ? ' · fallback clip' : ''}
                </span>
              </li>
            ))}
          </ul>
        ) : null}

        {error ? <div className="error">{error}</div> : null}
        {job?.error ? <div className="error">{job.error}</div> : null}
      </section>

      {showResults && job ? (
        <section className="results">
          <h2>Outcomes</h2>
          {job.recommendation ? (
            <div className="reco">
              <h3>Recommendation</h3>
              <p>{job.recommendation}</p>
            </div>
          ) : null}

          <div className="grid">
            {job.variants.map((v) => {
              const isReco =
                job.recommended_label && v.label === job.recommended_label && v.status === 'ok'
              return (
                <article key={v.variant_key} className={`card ${isReco ? 'recommended' : ''}`}>
                  <div className="card-head">
                    <h3>{v.label}</h3>
                    {isReco ? <span className="pill reco">Recommended</span> : <span className="pill">{v.status}</span>}
                  </div>
                  {v.status === 'ok' && v.video_url ? (
                    <div className="video-wrap">
                      <video src={v.video_url} controls playsInline preload="metadata" />
                    </div>
                  ) : (
                    <div className="video-wrap" style={{ display: 'grid', placeItems: 'center', color: '#94a3b8' }}>
                      {v.error || 'Unavailable'}
                    </div>
                  )}
                  <div className="card-body">
                    {v.mock_fallback
                      ? 'Played a fallback sample clip because the provider call did not return a video for this variant.'
                      : 'Short simulated outcome for this branch of the scenario.'}
                  </div>
                </article>
              )
            })}
          </div>
        </section>
      ) : null}

      <p className="footer-note">
        Async job flow: the server enqueues work and you poll for completion. No auth; state is kept in memory and
        resets on restart.
      </p>
    </div>
  )
}
