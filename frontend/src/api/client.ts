export async function apiRequest<T = any>(url: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(url, {
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    },
    ...options,
  })

  const text = await response.text()
  let data: any = null
  try {
    data = text ? JSON.parse(text) : {}
  } catch {
    throw new Error(text || `HTTP ${response.status}`)
  }

  if (!response.ok) {
    throw new Error(data?.msg || `HTTP ${response.status}`)
  }
  return data as T
}

export const apiGet = <T = any>(url: string) => apiRequest<T>(url)

export const apiPost = <T = any>(url: string, body: unknown) =>
  apiRequest<T>(url, {
    method: 'POST',
    body: JSON.stringify(body ?? {}),
  })
