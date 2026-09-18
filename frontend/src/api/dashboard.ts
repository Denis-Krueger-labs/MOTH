export interface DashboardHealth {
  status: string

  scheduler: {
    state: string
    running: boolean
  }

  retry_queue: {
    state: string
    retryable: number
    due: number
    active_leases: number
    oldest_retry_at: string | null
  }
}

export interface DashboardConnectivity {
  status: string
  reachable: boolean
  host: string
  port: number
  latency_ms: number | null
  greeting_received: boolean
  greeting_bytes?: number
}

export interface DashboardStats {
  unique_flags: number
  terminal: number
  retryable: number
  accepted: number
  gameserver_duplicate: number
  own: number
  old: number
  invalid: number
  active_leases: number
  due_retries: number
  retry_count_total: number
  oldest_retry_at: string | null
  event_count: number
  gameserver_attempts: number
  initial_submissions: number
  retry_attempts: number
  local_duplicates: number
  invalid_events: number
  mori_swats: number
  stale_retry_results: number
  initial_submissions_last_minute: number
  gameserver_attempts_last_minute: number
}

export interface DashboardEvent {
  id: number
  event_type: string
  code: string
  state: string
  service: string | null
  source: string | null
  worker_id: string | null
  event_count: number
  created_at: string
}

export interface DashboardRecent {
  count: number
  events: DashboardEvent[]
}

export interface FlagSubmissionRequest {
  flag: string
  service?: string
  source?: string
}

export interface FlagSubmissionResponse {
  status: string
  code: string
  message: string
  remembered?: boolean
}

function getErrorMessage(data: unknown): string | null {
  if (
    typeof data !== 'object' ||
    data === null ||
    !('detail' in data)
  ) {
    return null
  }

  const detail = data.detail

  if (typeof detail === 'string') {
    return detail
  }

  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => {
        if (
          typeof item === 'object' &&
          item !== null &&
          'msg' in item &&
          typeof item.msg === 'string'
        ) {
          return item.msg
        }

        return null
      })
      .filter((message): message is string => message !== null)

    if (messages.length > 0) {
      return messages.join(', ')
    }
  }

  return null
}

async function getJson<T>(
  url: string,
  options?: RequestInit,
): Promise<T> {
  const response = await fetch(url, options)

  const data: unknown = await response
    .json()
    .catch(() => null)

  if (!response.ok) {
    const apiMessage = getErrorMessage(data)

    throw new Error(
      apiMessage ??
        `Request failed: ${response.status} ${response.statusText}`,
    )
  }

  return data as T
}

export function getDashboardHealth(): Promise<DashboardHealth> {
  return getJson<DashboardHealth>(
    '/api/dashboard/health',
  )
}

export function getDashboardConnectivity(): Promise<DashboardConnectivity> {
  return getJson<DashboardConnectivity>(
    '/api/dashboard/connectivity',
  )
}

export function getDashboardStats(): Promise<DashboardStats> {
  return getJson<DashboardStats>(
    '/api/dashboard/stats',
  )
}

export function getDashboardRecent(
  limit = 20,
): Promise<DashboardRecent> {
  return getJson<DashboardRecent>(
    `/api/dashboard/recent?limit=${limit}`,
  )
}

export function submitFlag(
  flag: string,
): Promise<FlagSubmissionResponse> {
  const submission: FlagSubmissionRequest = {
    flag,
    source: 'dashboard-manual',
  }

  return getJson<FlagSubmissionResponse>(
    '/api/flags',
    {
      method: 'POST',

      headers: {
        'Content-Type': 'application/json',
      },

      body: JSON.stringify(submission),
    },
  )
}