import {
  useEffect,
  useState,
  type FormEvent,
} from 'react'

import './activity-terminal.css'
import './crt.css'
import './dashboard-composition.css'

import {
  getDashboardConnectivity,
  getDashboardHealth,
  getDashboardRecent,
  getDashboardStats,
  submitFlag,
  type DashboardConnectivity,
  type DashboardHealth,
  type DashboardRecent,
  type DashboardStats,
  type FlagSubmissionResponse,
} from './api/dashboard'

import ActivityTerminal from './components/ActivityTerminal'
import MoriFace from './components/MoriFace'

function App() {
  const [health, setHealth] =
    useState<DashboardHealth | null>(null)

  const [connectivity, setConnectivity] =
    useState<DashboardConnectivity | null>(null)

  const [stats, setStats] =
    useState<DashboardStats | null>(null)

  const [recent, setRecent] =
    useState<DashboardRecent | null>(null)

  const [healthError, setHealthError] =
    useState<string | null>(null)

  const [connectivityError, setConnectivityError] =
    useState<string | null>(null)

  const [statsError, setStatsError] =
    useState<string | null>(null)

  const [recentError, setRecentError] =
    useState<string | null>(null)

  const [flag, setFlag] =
    useState('')

  const [submissionResult, setSubmissionResult] =
    useState<FlagSubmissionResponse | null>(null)

  const [submissionError, setSubmissionError] =
    useState<string | null>(null)

  const [isSubmitting, setIsSubmitting] =
    useState(false)

  useEffect(() => {
    let cancelled = false

    let timer:
      ReturnType<typeof setTimeout> | null = null

    let cycle = 0

    async function pollDashboard() {
      const includeConnectivity =
        cycle % 3 === 0

      const healthRequest =
        getDashboardHealth()

      const statsRequest =
        getDashboardStats()

      const recentRequest =
        getDashboardRecent()

      const connectivityRequest =
        includeConnectivity
          ? getDashboardConnectivity()
          : Promise.resolve(null)

      const [
        healthResult,
        statsResult,
        recentResult,
        connectivityResult,
      ] = await Promise.allSettled([
        healthRequest,
        statsRequest,
        recentRequest,
        connectivityRequest,
      ])

      if (cancelled) {
        return
      }

      if (healthResult.status === 'fulfilled') {
        setHealth(healthResult.value)
        setHealthError(null)
      } else {
        setHealthError(
          healthResult.reason instanceof Error
            ? healthResult.reason.message
            : 'Unknown health error',
        )
      }

      if (statsResult.status === 'fulfilled') {
        setStats(statsResult.value)
        setStatsError(null)
      } else {
        setStatsError(
          statsResult.reason instanceof Error
            ? statsResult.reason.message
            : 'Unknown stats error',
        )
      }

      if (recentResult.status === 'fulfilled') {
        setRecent(recentResult.value)
        setRecentError(null)
      } else {
        setRecentError(
          recentResult.reason instanceof Error
            ? recentResult.reason.message
            : 'Unknown recent activity error',
        )
      }

      if (
        includeConnectivity &&
        connectivityResult.status === 'fulfilled' &&
        connectivityResult.value !== null
      ) {
        setConnectivity(
          connectivityResult.value,
        )

        setConnectivityError(null)
      } else if (
        includeConnectivity &&
        connectivityResult.status === 'rejected'
      ) {
        setConnectivityError(
          connectivityResult.reason instanceof Error
            ? connectivityResult.reason.message
            : 'Unknown connectivity error',
        )
      }

      cycle += 1

      timer = setTimeout(
        pollDashboard,
        2000,
      )
    }

    void pollDashboard()

    return () => {
      cancelled = true

      if (timer !== null) {
        clearTimeout(timer)
      }
    }
  }, [])

  async function refreshAfterSubmission() {
    const [
      healthResult,
      statsResult,
      recentResult,
    ] = await Promise.allSettled([
      getDashboardHealth(),
      getDashboardStats(),
      getDashboardRecent(),
    ])

    if (healthResult.status === 'fulfilled') {
      setHealth(healthResult.value)
      setHealthError(null)
    } else {
      setHealthError(
        healthResult.reason instanceof Error
          ? healthResult.reason.message
          : 'Unknown health error',
      )
    }

    if (statsResult.status === 'fulfilled') {
      setStats(statsResult.value)
      setStatsError(null)
    } else {
      setStatsError(
        statsResult.reason instanceof Error
          ? statsResult.reason.message
          : 'Unknown stats error',
      )
    }

    if (recentResult.status === 'fulfilled') {
      setRecent(recentResult.value)
      setRecentError(null)
    } else {
      setRecentError(
        recentResult.reason instanceof Error
          ? recentResult.reason.message
          : 'Unknown recent activity error',
      )
    }
  }

  async function handleManualSubmission(
    event: FormEvent<HTMLFormElement>,
  ) {
    event.preventDefault()

    const trimmedFlag = flag.trim()

    if (!trimmedFlag) {
      setSubmissionResult(null)

      setSubmissionError(
        'mof refuses to carry an empty flag',
      )

      return
    }

    setIsSubmitting(true)
    setSubmissionResult(null)
    setSubmissionError(null)

    try {
      const result = await submitFlag(trimmedFlag)

      setSubmissionResult(result)

      await refreshAfterSubmission()
    } catch (caughtError) {
      setSubmissionError(
        caughtError instanceof Error
          ? caughtError.message
          : 'Unknown submission error',
      )
    } finally {
      setIsSubmitting(false)
    }
  }

  const moriStatus = (() => {
    if (healthError) {
      return 'yelling at the nest'
    }

    if (connectivityError) {
      return 'lost sight of the gameserver'
    }

    if (
      health &&
      !health.scheduler.running
    ) {
      return 'noticed the scheduler sleeping'
    }

    if (
      health &&
      health.retry_queue.retryable > 0
    ) {
      return 'watching the retry pile'
    }

    if (
      connectivity &&
      !connectivity.reachable
    ) {
      return 'staring at port 6666'
    }

    if (
      connectivity?.reachable &&
      health?.status === 'healthy'
    ) {
      return 'approves. suspiciously.'
    }

    return 'judging quietly'
  })()

  return (
    <div className="moth-shell">
      <main className="page">
        <section className="hero">
          <span className="hero__eyebrow">
            ཐི༏ཋྀ MOTH control surface
          </span>

          <h1 className="hero__title">
            MOTH{' '}
            <span className="hero__title-accent">
              Dashboard
            </span>
          </h1>

          <p className="hero__text">
            Multi-Operator Transmission Hub.
            Mof carries the flags. MORI guards the nest.
          </p>

          <p className="mof-note">
            <MoriFace /> MORI is watching the transport layer.
          </p>
        </section>

        <section className="dashboard-section dashboard-section--status">
          <div
            className="dashboard-section__ghost"
            aria-hidden="true"
          >
            NEST
          </div>

          <div className="dashboard-section__header">
            <p className="dashboard-kicker">
              ./moth/status
            </p>

            <h2>
              System status
            </h2>
          </div>

          <div className="nest-layout">
            <div className="status-ledger">
              <div className="status-ledger__row">
                <span>MOTH API</span>

                <strong>
                  {healthError
                    ? 'error'
                    : health?.status ?? 'loading'}
                </strong>

                <small>
                  {healthError
                    ? healthError
                    : 'telemetry_access=allowed'}
                </small>
              </div>

              <div className="status-ledger__row">
                <span>Scheduler</span>

                <strong>
                  {health?.scheduler.state ?? 'loading'}
                </strong>

                <small>
                  scheduler_running=
                  {health
                    ? String(
                        health.scheduler.running,
                      )
                    : 'unknown'}
                </small>
              </div>

              <div className="status-ledger__row">
                <span>Retry queue</span>

                <strong>
                  {health?.retry_queue.state ?? 'loading'}
                </strong>

                <small>
                  retryable=
                  {health?.retry_queue.retryable ?? '—'}
                  {' '}
                  due=
                  {health?.retry_queue.due ?? '—'}
                </small>
              </div>
            </div>

            <aside className="mori-presence">
              <span className="mori-presence__label">
                MORI
              </span>

              <div className="mori-presence__face">
                <MoriFace />
              </div>

              <p>
                {moriStatus}
              </p>

              <span
                className="mori-presence__sigil"
                aria-hidden="true"
              >
                ࿔‧ ֶָ֢˚˖𐦍˖˚ֶָ֢ ‧࿔
              </span>
            </aside>
          </div>
        </section>

        <section className="dashboard-section dashboard-section--transmissions">
          <div
            className="dashboard-section__ghost"
            aria-hidden="true"
          >
            TRANSMISSIONS
          </div>

          <div className="dashboard-section__header">
            <p className="dashboard-kicker">
              ./transport/telemetry
            </p>

            <h2>
              Submission statistics
            </h2>
          </div>

          <div className="metric-strip">
            <div className="metric">
              <strong>
                {stats?.gameserver_attempts ?? '—'}
              </strong>

              <span>
                attempts
              </span>

              <small>
                initial=
                {stats?.initial_submissions ?? '—'}
              </small>
            </div>

            <div className="metric">
              <strong>
                {stats?.accepted ?? '—'}
              </strong>

              <span>
                accepted
              </span>

              <small>
                unique=
                {stats?.unique_flags ?? '—'}
              </small>
            </div>

            <div className="metric">
              <strong>
                {stats?.retry_count_total ?? '—'}
              </strong>

              <span>
                retries
              </span>

              <small>
                attempts=
                {stats?.retry_attempts ?? '—'}
              </small>
            </div>

            <div className="metric">
              <strong>
                {stats?.active_leases ?? '—'}
              </strong>

              <span>
                active leases
              </span>

              <small>
                due=
                {stats?.due_retries ?? '—'}
              </small>
            </div>
          </div>

          {statsError && (
            <p className="dashboard-error">
              stats_error={statsError}
            </p>
          )}
        </section>

        <section className="dashboard-section dashboard-section--operations">
          <div
            className="dashboard-section__ghost"
            aria-hidden="true"
          >
            OFFERING
          </div>

          <div className="operations-grid">
            <div className="operation-block">
              <p className="dashboard-kicker">
                ./gameserver/probe
              </p>

              <h2>
                Gameserver
              </h2>

              <div className="probe-readout">
                <p>
                  <span>target</span>

                  <strong>
                    {connectivity
                      ? `${connectivity.host}:${connectivity.port}`
                      : '—'}
                  </strong>
                </p>

                <p>
                  <span>reachable</span>

                  <strong>
                    {connectivityError
                      ? 'error'
                      : connectivity
                        ? String(
                            connectivity.reachable,
                          )
                        : 'unknown'}
                  </strong>
                </p>

                <p>
                  <span>
                    greeting_received
                  </span>

                  <strong>
                    {connectivity
                      ? String(
                          connectivity.greeting_received,
                        )
                      : 'unknown'}
                  </strong>
                </p>

                <p>
                  <span>
                    greeting_bytes
                  </span>

                  <strong>
                    {connectivity?.greeting_bytes ?? 'n/a'}
                  </strong>
                </p>

                <p>
                  <span>
                    latency_ms
                  </span>

                  <strong>
                    {connectivity?.latency_ms ?? 'n/a'}
                  </strong>
                </p>
              </div>
            </div>

            <div className="operation-block operation-block--manual">
              <p className="dashboard-kicker">
                ./moth/offer
              </p>

              <h2>
                Manual offering
              </h2>

              <form
                className="offering-form"
                onSubmit={handleManualSubmission}
              >
                <label htmlFor="manual-flag">
                  <span>$</span> send
                </label>

                <div className="offering-form__line">
                  <input
                    id="manual-flag"
                    className="input"
                    type="text"
                    value={flag}
                    onChange={(event) => {
                      setFlag(event.target.value)
                    }}
                    placeholder="FAUST_..."
                    autoComplete="off"
                    spellCheck={false}
                    disabled={isSubmitting}
                  />

                  <button
                    className="button button--primary"
                    type="submit"
                    disabled={isSubmitting}
                  >
                    {isSubmitting
                      ? 'Mof is carrying...'
                      : 'Send with Mof'}
                  </button>
                </div>
              </form>

              <p className="offering-source">
                source=dashboard-manual ཐི༏ཋྀ
              </p>

              {submissionResult && (
                <div
                  className="submission-response"
                  aria-live="polite"
                >
                  <strong>
                    {submissionResult.status}
                  </strong>

                  <span>
                    code=
                    {submissionResult.code}
                  </span>

                  <span>
                    {submissionResult.message}
                  </span>

                  {submissionResult.remembered !==
                    undefined && (
                    <span>
                      remembered=
                      {String(
                        submissionResult.remembered,
                      )}
                    </span>
                  )}
                </div>
              )}

              {submissionError && (
                <div
                  className="submission-response submission-response--error"
                  aria-live="polite"
                >
                  <strong>
                    MORI rejected the offering
                  </strong>

                  <span>
                    {submissionError}
                  </span>
                </div>
              )}
            </div>
          </div>
        </section>

        <section className="dashboard-section dashboard-section--events">
          <div
            className="dashboard-section__ghost"
            aria-hidden="true"
          >
            EVENTS
          </div>

          <div className="dashboard-section__header">
            <p className="dashboard-kicker">
              ./moth/events
            </p>

            <h2>
              Recent activity
            </h2>
          </div>

          <ActivityTerminal
            recent={recent}
            error={recentError}
          />
        </section>
      </main>
    </div>
  )
}

export default App