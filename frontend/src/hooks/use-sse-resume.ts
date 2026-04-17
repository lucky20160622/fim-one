"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { useSSE, type SSEMessage, type StartOptions } from "@/hooks/use-sse"
import { getApiDirectUrl, ACCESS_TOKEN_KEY } from "@/lib/constants"

/**
 * High-level state of the auto-resume machinery.
 *
 * - ``idle``         — no stream has started yet (or we finished cleanly)
 * - ``running``      — a live stream is in progress
 * - ``reconnecting`` — stream disconnected, attempting ``/chat/resume``
 * - ``failed``       — exhausted ``maxRetries`` without a successful resume
 */
export type ResumeState = "idle" | "running" | "reconnecting" | "failed"

export interface UseSseResumeOptions {
  /**
   * Conversation ID the stream is bound to. Required to enable resume —
   * if omitted, the hook degrades to plain ``useSSE`` behaviour.
   */
  conversationId?: string
  /** Default: 3 */
  maxRetries?: number
  /** Default: [300, 1000, 3000] ms */
  backoffMs?: (attempt: number) => number
  /**
   * Fetch implementation. Injected for testing — in production this
   * defaults to the global ``fetch``. Must support ``AbortSignal``.
   */
  fetchFn?: typeof fetch
  /**
   * API base URL for the resume endpoint. Defaults to
   * ``getApiDirectUrl()``. Overridable for tests.
   */
  apiBaseUrl?: string
  /**
   * Access token accessor. Defaults to reading ``ACCESS_TOKEN_KEY``
   * from ``localStorage``. Overridable for tests.
   */
  getAccessToken?: () => string | null
}

export interface UseSseResumeReturn {
  messages: SSEMessage[]
  isRunning: boolean
  isError: boolean
  resumeState: ResumeState
  resumeAttempt: number
  start: (url: string, options?: StartOptions) => void
  abort: () => void
  reset: () => void
}

const DEFAULT_BACKOFF = [300, 1000, 3000]

/**
 * Wraps ``useSSE`` with cursor-aware automatic resume.
 *
 * When the underlying stream terminates with ``abortReason === "network"``
 * the hook fires ``POST /api/chat/resume`` with the last seen cursor,
 * merges replayed frames back into ``messages`` in order, and exits the
 * reconnecting state upon a ``resume_done`` frame. After
 * ``maxRetries`` consecutive failures it surfaces ``resumeState="failed"``.
 *
 * Server-side dedup is authoritative: we send ``lastCursor`` and trust
 * the backend to only replay frames with ``cursor > lastCursor``.
 */
export function useSseResume(
  opts: UseSseResumeOptions = {},
): UseSseResumeReturn {
  const {
    conversationId,
    maxRetries = 3,
    backoffMs = (attempt) => DEFAULT_BACKOFF[Math.min(attempt, DEFAULT_BACKOFF.length - 1)] ?? 3000,
    fetchFn,
    apiBaseUrl,
    getAccessToken,
  } = opts

  const sse = useSSE()
  const { start: startInner, abort: abortInner, reset: resetInner, appendMessages, lastCursorRef } = sse

  const [resumeState, setResumeState] = useState<ResumeState>("idle")
  const [resumeAttempt, setResumeAttempt] = useState(0)
  const resumeAbortRef = useRef<AbortController | null>(null)
  const resumeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  // Preserve the last start() invocation so ``onError`` / error state is
  // threaded through replay attempts consistently.
  const lastStartOptionsRef = useRef<StartOptions | undefined>(undefined)
  // Synchronous guard — setState is async but we need to short-circuit
  // "abort during resume" immediately.
  const abortedRef = useRef(false)

  const clearResumeTimer = useCallback(() => {
    if (resumeTimerRef.current !== null) {
      clearTimeout(resumeTimerRef.current)
      resumeTimerRef.current = null
    }
  }, [])

  const cancelResume = useCallback(() => {
    clearResumeTimer()
    if (resumeAbortRef.current) {
      resumeAbortRef.current.abort()
      resumeAbortRef.current = null
    }
  }, [clearResumeTimer])

  // Clean up any pending retry timer on unmount
  useEffect(() => {
    return () => {
      cancelResume()
    }
  }, [cancelResume])

  /**
   * Parse a full SSE payload text into individual frames. Used while
   * streaming the resume response body.
   */
  const parseAndAppend = useCallback(
    (buffer: string, leftover: { value: string }): boolean => {
      // Returns true if a ``resume_done`` frame was observed.
      const full = leftover.value + buffer
      const lines = full.split("\n")
      leftover.value = lines.pop() ?? ""

      let currentEvent = "message"
      let currentData = ""
      const appended: SSEMessage[] = []
      let sawResumeDone = false

      for (const line of lines) {
        if (line.startsWith("event:")) {
          currentEvent = line.slice(6).trim()
        } else if (line.startsWith("data:")) {
          currentData = line.slice(5).trim()
        } else if (line === "") {
          if (currentData) {
            try {
              const parsed: unknown = JSON.parse(currentData)
              let cursor: number | undefined
              let unwrapped: unknown = parsed
              if (parsed && typeof parsed === "object") {
                const maybe = parsed as { cursor?: unknown; data?: unknown }
                if (typeof maybe.cursor === "number") {
                  cursor = maybe.cursor
                  if ("data" in maybe) {
                    unwrapped = maybe.data
                  }
                }
              }
              if (currentEvent === "resume_done") {
                sawResumeDone = true
                // Still surface the resume_done marker so consumers may
                // inspect it (e.g. telemetry). It's not a data event.
                appended.push({
                  event: "resume_done",
                  data: unwrapped,
                  timestamp: Date.now(),
                  cursor,
                })
              } else {
                appended.push({
                  event: currentEvent,
                  data: unwrapped,
                  timestamp: Date.now(),
                  cursor,
                })
              }
            } catch {
              // ignore malformed frames
            }
          }
          currentEvent = "message"
          currentData = ""
        }
      }

      if (appended.length > 0) {
        appendMessages(appended)
      }
      return sawResumeDone
    },
    [appendMessages],
  )

  const performResume = useCallback(
    async (): Promise<"ok" | "retry" | "aborted"> => {
      if (!conversationId) return "aborted"
      if (abortedRef.current) return "aborted"

      const controller = new AbortController()
      resumeAbortRef.current = controller

      const base = apiBaseUrl ?? getApiDirectUrl()
      const tokenGetter = getAccessToken
        ?? (() => (typeof window !== "undefined" ? localStorage.getItem(ACCESS_TOKEN_KEY) : null))
      const token = tokenGetter()
      const fetchImpl = fetchFn ?? (typeof fetch !== "undefined" ? fetch : null)
      if (!fetchImpl) return "retry"

      try {
        const res = await fetchImpl(`${base}/api/chat/resume`, {
          method: "POST",
          signal: controller.signal,
          headers: {
            "Content-Type": "application/json",
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: JSON.stringify({
            conversation_id: conversationId,
            cursor: lastCursorRef.current,
          }),
        })

        if (!res.ok || !res.body) {
          return "retry"
        }

        const reader = res.body.getReader()
        const decoder = new TextDecoder()
        const leftover = { value: "" }
        let sawResumeDone = false

        while (true) {
          if (abortedRef.current) {
            try {
              await reader.cancel()
            } catch {
              /* ignore */
            }
            return "aborted"
          }
          const { done, value } = await reader.read()
          if (done) break
          const chunk = decoder.decode(value, { stream: true })
          if (parseAndAppend(chunk, leftover)) {
            sawResumeDone = true
          }
        }

        // Flush any trailing buffered line (shouldn't happen with a
        // well-formed SSE stream, but be defensive).
        if (leftover.value.length > 0) {
          if (parseAndAppend("\n\n", leftover)) {
            sawResumeDone = true
          }
        }

        // If the server produced no events and no resume_done marker
        // (shouldn't happen — the endpoint always closes with one) we
        // still treat it as success rather than thrash.
        void sawResumeDone
        return "ok"
      } catch (err: unknown) {
        if ((err as { name?: string })?.name === "AbortError") return "aborted"
        return "retry"
      } finally {
        if (resumeAbortRef.current === controller) {
          resumeAbortRef.current = null
        }
      }
    },
    [apiBaseUrl, conversationId, fetchFn, getAccessToken, lastCursorRef, parseAndAppend],
  )

  const scheduleResume = useCallback(
    (attempt: number) => {
      if (abortedRef.current) return
      if (!conversationId) {
        setResumeState("failed")
        return
      }
      if (attempt > maxRetries) {
        setResumeState("failed")
        return
      }

      setResumeState("reconnecting")
      setResumeAttempt(attempt)

      const delay = backoffMs(attempt - 1)
      resumeTimerRef.current = setTimeout(async () => {
        resumeTimerRef.current = null
        const outcome = await performResume()
        if (outcome === "aborted") {
          return
        }
        if (outcome === "ok") {
          setResumeState("idle")
          setResumeAttempt(0)
          return
        }
        // "retry"
        scheduleResume(attempt + 1)
      }, delay)
    },
    [backoffMs, conversationId, maxRetries, performResume],
  )

  const start = useCallback(
    (url: string, options?: StartOptions) => {
      abortedRef.current = false
      setResumeState("running")
      setResumeAttempt(0)
      cancelResume()
      lastStartOptionsRef.current = options

      const wrapped: StartOptions = {
        ...options,
        onDisconnect: (cursor) => {
          options?.onDisconnect?.(cursor)
          if (!conversationId) {
            setResumeState("failed")
            return
          }
          if (abortedRef.current) return
          scheduleResume(1)
        },
      }
      startInner(url, wrapped)
    },
    [cancelResume, conversationId, scheduleResume, startInner],
  )

  const abort = useCallback(() => {
    abortedRef.current = true
    cancelResume()
    abortInner()
    setResumeState("idle")
    setResumeAttempt(0)
  }, [abortInner, cancelResume])

  const reset = useCallback(() => {
    abortedRef.current = false
    cancelResume()
    resetInner()
    setResumeState("idle")
    setResumeAttempt(0)
  }, [cancelResume, resetInner])

  // If the underlying stream finishes cleanly (isRunning=false, no
  // network abort), advance to idle so the indicator clears.
  useEffect(() => {
    if (!sse.isRunning && resumeState === "running") {
      setResumeState("idle")
    }
  }, [sse.isRunning, resumeState])

  const isError = sse.isError || resumeState === "failed"

  return {
    messages: sse.messages,
    isRunning: sse.isRunning || resumeState === "reconnecting",
    isError,
    resumeState,
    resumeAttempt,
    start,
    abort,
    reset,
  }
}
