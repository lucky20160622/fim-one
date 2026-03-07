import { ApiError } from "./api"

/**
 * Extract a user-friendly, translated error message from an error object.
 *
 * When the backend returns a structured `error_code`, this function looks up
 * the corresponding translation via the supplied `next-intl` translator (`tError`).
 * Falls back to the raw `err.message` if no translation is found.
 *
 * Usage:
 *   const tError = useTranslations("errors")
 *   toast.error(getErrorMessage(err, tError))
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type TranslatorFn = (key: string, args?: Record<string, any>) => string

export function getErrorMessage(
  err: unknown,
  tError: TranslatorFn,
): string {
  if (err instanceof ApiError && err.errorCode) {
    const translated = tError(err.errorCode, err.errorArgs as Record<string, string | number>)
    // next-intl returns the key itself when no translation is found
    if (translated !== err.errorCode) return translated
  }
  return err instanceof Error ? err.message : tError("_fallback")
}
