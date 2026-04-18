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

function operationalSummary(variantKey: string): {
  safetyRisk: string
  missionSuccess: string
  intervention: string
} {
  switch (variantKey) {
    case 'best_case':
      return { safetyRisk: 'Low', missionSuccess: 'High', intervention: 'None' }
    case 'worst_case':
      return { safetyRisk: 'High', missionSuccess: 'Low', intervention: 'Immediate' }
    case 'edge_case':
      return { safetyRisk: 'Medium', missionSuccess: 'Medium', intervention: 'Likely' }
    default:
      return { safetyRisk: 'Unknown', missionSuccess: 'Unknown', intervention: 'Unknown' }
  }
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
      <div className="page-glow page-glow-a" />
      <div className="page-glow page-glow-b" />
      <header className="hero">
        <div className="hero-copy">
          <span className="eyebrow">Track 4 · qualitative simulation</span>
          <h1>ScenarioSim</h1>
          <p>
            Turn one operational situation into three short, decision-ready outcome clips: best case, worst case,
            and the edge path teams forget to plan for.
          </p>
        </div>
        <div className="hero-card">
          <span className="hero-card-label">What you get</span>
          <ul>
            <li>Three comparable video branches</li>
            <li>Recommendation for decision-making</li>
            <li>Track 4 export with provenance + weak labels</li>
          </ul>
        </div>
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
          {jobId ? (
            <p className="export-link">
              <a href={`${apiBase}/api/jobs/${jobId}/export`} target="_blank" rel="noreferrer">
                Export run as JSON (Track 4 — weak labels + provenance)
              </a>
            </p>
          ) : null}
          {job.recommendation ? (
            <div className="reco">
              <h3>Recommendation</h3>
              <p>{job.recommendation}</p>
            </div>
          ) : null}

          <div className="scorecard">
            <div className="scorecard-head">
              <div>
                <h3>Decision summary</h3>
                <p>Weak operational tags that help a team triage each branch quickly.</p>
              </div>
            </div>
            <div className="scorecard-grid">
              {job.variants.map((v) => {
                const summary = operationalSummary(v.variant_key)
                return (
                  <article key={`${v.variant_key}-summary`} className="scorecard-item">
                    <div className="scorecard-item-head">
                      <strong>{v.label}</strong>
                      <span className={`pill subtle ${v.status === 'ok' ? 'ok' : v.status === 'failed' ? 'fail' : ''}`}>
                        {v.status}
                      </span>
                    </div>
                    <dl>
                      <div>
                        <dt>Safety risk</dt>
                        <dd>{summary.safetyRisk}</dd>
                      </div>
                      <div>
                        <dt>Mission success</dt>
                        <dd>{summary.missionSuccess}</dd>
                      </div>
                      <div>
                        <dt>Intervention</dt>
                        <dd>{summary.intervention}</dd>
                      </div>
                    </dl>
                  </article>
                )
              })}
            </div>
          </div>

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
                      ? 'Fallback clip used so the branch still completes for review.'
                      : 'Short simulated branch for comparison and review.'}
                  </div>
                </article>
              )
            })}
          </div>
        </section>
      ) : null}

      <p className="footer-note">
        Async jobs; in-memory store (lost on restart). Track 4: use <strong>Export JSON</strong> for pipeline-friendly
        bundles. Batch API: <code>POST /api/jobs/batch</code>.
      </p>
    </div>
  )
}
