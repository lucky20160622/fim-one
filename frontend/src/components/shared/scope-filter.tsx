"use client"

import { useTranslations } from "next-intl"
import type { ScopeValue } from "@/hooks/use-scope-filter"

interface ScopeFilterProps {
  value: ScopeValue
  onChange: (scope: ScopeValue) => void
}

const SCOPES: ScopeValue[] = ["all", "mine", "org", "installed"]

const SCOPE_LABELS: Record<ScopeValue, string> = {
  all: "all",
  mine: "mine",
  org: "fromOrg",
  installed: "installed",
}

export function ScopeFilter({ value, onChange }: ScopeFilterProps) {
  const tc = useTranslations("common")

  return (
    <div className="flex items-center gap-1.5">
      {SCOPES.map((key) => (
        <button
          key={key}
          onClick={() => onChange(key)}
          className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
            value === key
              ? "bg-primary text-primary-foreground"
              : "bg-muted text-muted-foreground hover:text-foreground"
          }`}
        >
          {tc(SCOPE_LABELS[key])}
        </button>
      ))}
    </div>
  )
}
