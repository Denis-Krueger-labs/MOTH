import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react'

import {
  afterEach,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from 'vitest'

import App from './App'

import {
  getDashboardConnectivity,
  getDashboardHealth,
  getDashboardRecent,
  getDashboardStats,
  submitFlag,
} from './api/dashboard'

vi.mock('./api/dashboard', async () => {
  const actual = await vi.importActual<
    typeof import('./api/dashboard')
  >('./api/dashboard')

  return {
    ...actual,

    getDashboardHealth: vi.fn(),
    getDashboardConnectivity: vi.fn(),
    getDashboardStats: vi.fn(),
    getDashboardRecent: vi.fn(),
    submitFlag: vi.fn(),
  }
})

const mockedHealth =
  vi.mocked(getDashboardHealth)

const mockedConnectivity =
  vi.mocked(getDashboardConnectivity)

const mockedStats =
  vi.mocked(getDashboardStats)

const mockedRecent =
  vi.mocked(getDashboardRecent)

const mockedSubmitFlag =
  vi.mocked(submitFlag)

const healthResponse = {
  status: 'healthy',

  scheduler: {
    state: 'running',
    running: true,
  },

  retry_queue: {
    state: 'clear',
    retryable: 0,
    due: 0,
    active_leases: 0,
    oldest_retry_at: null,
  },
}

const connectivityResponse = {
  status: 'reachable',
  reachable: true,
  host: '127.0.0.1',
  port: 6666,
  latency_ms: 1.23,
  greeting_received: true,
  greeting_bytes: 29,
}

const statsResponse = {
  unique_flags: 42,
  terminal: 42,
  retryable: 0,
  accepted: 42,
  gameserver_duplicate: 0,
  own: 0,
  old: 0,
  invalid: 0,
  active_leases: 0,
  due_retries: 0,
  retry_count_total: 3,
  oldest_retry_at: null,
  event_count: 45,
  gameserver_attempts: 45,
  initial_submissions: 42,
  retry_attempts: 3,
  local_duplicates: 0,
  invalid_events: 0,
  mori_swats: 0,
  stale_retry_results: 0,
  initial_submissions_last_minute: 2,
  gameserver_attempts_last_minute: 2,
}

const recentResponse = {
  count: 1,

  events: [
    {
      id: 1,
      event_type: 'submission',
      code: 'OK',
      state: 'terminal',
      service: null,
      source: 'dashboard-manual',
      worker_id: null,
      event_count: 1,
      created_at:
        '2026-09-18T07:00:00+00:00',
    },
  ],
}

function prepareSuccessfulDashboard() {
  mockedHealth.mockResolvedValue(
    healthResponse,
  )

  mockedConnectivity.mockResolvedValue(
    connectivityResponse,
  )

  mockedStats.mockResolvedValue(
    statsResponse,
  )

  mockedRecent.mockResolvedValue(
    recentResponse,
  )
}

describe('MOTH dashboard', () => {
  beforeEach(() => {
    vi.useRealTimers()

    prepareSuccessfulDashboard()
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('loads live operational state', async () => {
    render(<App />)

    expect(
      screen.getByText('System status'),
    ).toBeInTheDocument()

    await waitFor(() => {
      expect(
        screen.getByText('healthy'),
      ).toBeInTheDocument()
    })

    expect(
      screen.getByText('running'),
    ).toBeInTheDocument()

    expect(
      screen.getByText('clear'),
    ).toBeInTheDocument()

    expect(
      screen.getByText(
        'approves. suspiciously.',
      ),
    ).toBeInTheDocument()

    expect(
      screen.getByText('127.0.0.1:6666'),
    ).toBeInTheDocument()

    expect(
      screen.getByText('45'),
    ).toBeInTheDocument()

    expect(
      screen.getByText('42'),
    ).toBeInTheDocument()
  })

  it('submits a manual flag through MOTH', async () => {
    mockedSubmitFlag.mockResolvedValue({
      status: 'submitted',
      code: 'OK',
      message: 'stress-test',
      remembered: true,
    })

    render(<App />)

    const input =
      await screen.findByLabelText('Flag')

    fireEvent.change(input, {
      target: {
        value:
          '  FAUST_12345678901234567890123456789012  ',
      },
    })

    fireEvent.click(
      screen.getByRole('button', {
        name: 'Send with Mof',
      }),
    )

    await waitFor(() => {
      expect(
        mockedSubmitFlag,
      ).toHaveBeenCalledWith(
        'FAUST_12345678901234567890123456789012',
      )
    })

    expect(
      await screen.findByText('submitted'),
    ).toBeInTheDocument()

    expect(
      screen.getByText('code=OK'),
    ).toBeInTheDocument()

    expect(
      screen.getByText('stress-test'),
    ).toBeInTheDocument()

    expect(
      screen.getByText('remembered=true'),
    ).toBeInTheDocument()
  })

  it('refuses an empty manual offering locally', async () => {
    render(<App />)

    const button =
      await screen.findByRole(
        'button',
        {
          name: 'Send with Mof',
        },
      )

    fireEvent.click(button)

    expect(
      await screen.findByText(
        'MORI rejected the offering',
      ),
    ).toBeInTheDocument()

    expect(
      screen.getByText(
        'mof refuses to carry an empty flag',
      ),
    ).toBeInTheDocument()

    expect(
      mockedSubmitFlag,
    ).not.toHaveBeenCalled()
  })

  it('refreshes dashboard state after a manual submission', async () => {
    mockedSubmitFlag.mockResolvedValue({
      status: 'submitted',
      code: 'OK',
      message: 'accepted',
      remembered: true,
    })

    render(<App />)

    await waitFor(() => {
      expect(
        mockedStats,
      ).toHaveBeenCalledTimes(1)
    })

    const input =
      screen.getByLabelText('Flag')

    fireEvent.change(input, {
      target: {
        value:
          'FAUST_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
      },
    })

    fireEvent.click(
      screen.getByRole('button', {
        name: 'Send with Mof',
      }),
    )

    await waitFor(() => {
      expect(
        mockedStats.mock.calls.length,
      ).toBeGreaterThanOrEqual(2)
    })

    expect(
      mockedHealth.mock.calls.length,
    ).toBeGreaterThanOrEqual(2)

    expect(
      mockedRecent.mock.calls.length,
    ).toBeGreaterThanOrEqual(2)
  })

  it('continues polling after the initial dashboard load', async () => {
    vi.useFakeTimers()

    render(<App />)

    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(
      mockedHealth,
    ).toHaveBeenCalledTimes(1)

    expect(
      mockedStats,
    ).toHaveBeenCalledTimes(1)

    expect(
      mockedRecent,
    ).toHaveBeenCalledTimes(1)

    expect(
      mockedConnectivity,
    ).toHaveBeenCalledTimes(1)

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000)
    })

    expect(
      mockedHealth,
    ).toHaveBeenCalledTimes(2)

    expect(
      mockedStats,
    ).toHaveBeenCalledTimes(2)

    expect(
      mockedRecent,
    ).toHaveBeenCalledTimes(2)

    expect(
      mockedConnectivity,
    ).toHaveBeenCalledTimes(1)
  })

  it('shows gameserver failure without losing other dashboard state', async () => {
    mockedConnectivity.mockResolvedValue({
      ...connectivityResponse,

      status: 'unreachable',
      reachable: false,
      latency_ms: null,
      greeting_received: false,
      greeting_bytes: undefined,
    })

    render(<App />)

    await waitFor(() => {
      expect(
        screen.getByText(
          'staring at port 6666',
        ),
      ).toBeInTheDocument()
    })

    expect(
      screen.getByText('healthy'),
    ).toBeInTheDocument()

    expect(
      screen.getByText('running'),
    ).toBeInTheDocument()

    const reachableLabel =
      screen.getByText('reachable')

    const reachableRow =
      reachableLabel.closest('p')

    expect(
      reachableRow,
    ).not.toBeNull()

    expect(
      within(reachableRow!).getByText(
        'false',
      ),
    ).toBeInTheDocument()
  })
})