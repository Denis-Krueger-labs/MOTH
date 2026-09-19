import {
  render,
  screen,
} from '@testing-library/react'

import {
  describe,
  expect,
  it,
} from 'vitest'

import ActivityTerminal from './ActivityTerminal'

describe('ActivityTerminal', () => {
  it('renders recent operational events', () => {
    render(
      <ActivityTerminal
        error={null}
        recent={{
          count: 1,

          events: [
            {
              id: 7,
              event_type: 'submission',
              code: 'OK',
              state: 'terminal',
              service: 'flags',
              source: 'dashboard-manual',
              worker_id: null,
              event_count: 1,
              created_at:
                '2026-09-18T07:00:00+00:00',
            },
          ],
        }}
      />,
    )

    expect(
      screen.getByText(
        /submission code=OK state=terminal/,
      ),
    ).toBeInTheDocument()

    expect(
      screen.getByText(
        /source=dashboard-manual/,
      ),
    ).toBeInTheDocument()

    expect(
      screen.getByText(
        /service=flags/,
      ),
    ).toBeInTheDocument()

    expect(
      screen.getByText(
        /showing=1 latest events/,
      ),
    ).toBeInTheDocument()
  })

  it('renders an API error safely', () => {
    render(
      <ActivityTerminal
        recent={null}
        error="MORI lost the event stream"
      />,
    )

    expect(
      screen.getByText(
        /error=MORI lost the event stream/,
      ),
    ).toBeInTheDocument()
  })

  it('renders an empty event stream', () => {
    render(
      <ActivityTerminal
        error={null}
        recent={{
          count: 0,
          events: [],
        }}
      />,
    )

    expect(
      screen.getByText(
        /no_events_yet=true/,
      ),
    ).toBeInTheDocument()

    expect(
      screen.getByText(
        /showing=0 latest events/,
      ),
    ).toBeInTheDocument()
  })
})