import type {
  DashboardEvent,
  DashboardRecent,
} from '../api/dashboard'

type ActivityTerminalProps = {
  recent: DashboardRecent | null
  error: string | null
}

function formatEventTime(createdAt: string): string {
  return new Date(createdAt).toLocaleString(
    undefined,
    {
      hour12: false,
    },
  )
}

function formatEvent(event: DashboardEvent): string {
  const parts = [
    event.event_type,
    `code=${event.code}`,
    `state=${event.state}`,
    `source=${event.source ?? 'unknown'}`,
  ]

  if (event.service) {
    parts.push(`service=${event.service}`)
  }

  if (event.event_count !== 1) {
    parts.push(`count=${event.event_count}`)
  }

  return parts.join(' ')
}

function ActivityTerminal({
  recent,
  error,
}: ActivityTerminalProps) {
  return (
    <div
      className="activity-terminal"
      aria-label="Recent MOTH activity"
    >
      <div className="activity-terminal__chrome">
        <p>mof@nest:~/events</p>

        <span className="activity-terminal__status">
          live event stream
        </span>

        <div
          className="activity-terminal__dots"
          aria-hidden="true"
        >
          <span />
          <span />
          <span />
        </div>
      </div>

      <div className="activity-terminal__screen">
        <p className="activity-terminal__system">
          <span>#</span>{' '}
          MOTH event stream mounted read-only.
        </p>

        <p className="activity-terminal__command">
          <span>$</span>{' '}
          tail -f ./moth/events.log
        </p>

        {error && (
          <p className="activity-terminal__line">
            <span>&gt;</span>{' '}
            error={error}
          </p>
        )}

        {!error && !recent && (
          <p className="activity-terminal__line">
            <span>&gt;</span>{' '}
            waiting_for_events=true
          </p>
        )}

        {recent?.events.map((event) => (
          <p
            className="activity-terminal__line"
            key={event.id}
          >
            <span>&gt;</span>{' '}
            <time dateTime={event.created_at}>
              [{formatEventTime(event.created_at)}]
            </time>{' '}
            {formatEvent(event)}
          </p>
        ))}

        {recent &&
          recent.events.length === 0 && (
            <p className="activity-terminal__line">
              <span>&gt;</span>{' '}
              no_events_yet=true
            </p>
          )}

        {recent && (
          <p className="activity-terminal__prompt">
            <span>$</span>{' '}
            showing={recent.count} latest events
          </p>
        )}
      </div>
    </div>
  )
}

export default ActivityTerminal