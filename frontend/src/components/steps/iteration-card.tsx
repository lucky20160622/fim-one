"use client"

import { useState } from "react"
import { Loader2 } from "lucide-react"
import { Card, CardContent } from "@/components/ui/card"
import { cn } from "@/lib/utils"
import type { IterationData } from "./types"
import { IterationHeader } from "./iteration-header"
import { ToolArgsBlock } from "./tool-args-block"
import { ObservationBlock } from "./observation-block"
import { ErrorBlock } from "./error-block"
import { generateStepSummary } from "./step-summary"

type TabKey = "args" | "obs"

interface IterationCardProps {
  data: IterationData
  summary?: string
  size?: "default" | "compact"
  variant?: "card" | "inline"
  defaultCollapsed?: boolean
  showReasoning?: boolean
}

export function IterationCard({
  data,
  summary: summaryProp,
  size = "default",
  variant = "card",
  defaultCollapsed = true,
  showReasoning = false,
}: IterationCardProps) {
  const isLoading = data.loading || data.type === "tool_start"
  const hasArgs = data.tool_args && Object.keys(data.tool_args).length > 0
  const hasObs = !!data.observation
  const hasError = !!data.error
  const hasTabs = (hasArgs || hasObs) && !isLoading

  // null = all collapsed; "args" or "obs" = that tab active
  const [activeTab, setActiveTab] = useState<TabKey | null>(
    defaultCollapsed ? null : (hasArgs ? "args" : hasObs ? "obs" : null),
  )

  const toggleTab = (tab: TabKey) => {
    setActiveTab((cur) => (cur === tab ? null : tab))
  }

  // Auto-generate summary if not provided
  const summary = summaryProp ?? (
    (data.type === "tool_call" || data.type === "tool_start")
      ? generateStepSummary(data.tool_name, data.tool_args, data.reasoning)
      : undefined
  )

  // Build tab items
  const tabs: { key: TabKey; label: string; available: boolean }[] = [
    { key: "args", label: "Arguments", available: !!hasArgs },
    { key: "obs", label: "Observation", available: !!hasObs },
  ]

  const content = (
    <div className="space-y-1.5">
      <IterationHeader data={data} summary={summary} />

      {showReasoning && data.reasoning && (
        <p className="text-[11px] italic text-muted-foreground leading-relaxed">
          {data.reasoning}
        </p>
      )}

      {isLoading && (
        <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
          <Loader2 className="h-2.5 w-2.5 animate-spin" />
          <span className="shiny-text">Executing…</span>
        </div>
      )}

      {/* Tab bar */}
      {hasTabs && (
        <div className="flex items-center gap-px rounded border border-border/40 bg-muted/20 w-fit overflow-hidden">
          {tabs.filter((t) => t.available).map((t) => (
            <button
              key={t.key}
              type="button"
              onClick={() => toggleTab(t.key)}
              className={cn(
                "px-2.5 py-1 text-[10px] font-medium uppercase tracking-wider transition-colors",
                activeTab === t.key
                  ? "bg-amber-500/15 text-amber-500"
                  : "text-muted-foreground hover:bg-muted/40",
              )}
            >
              {t.label}
            </button>
          ))}
        </div>
      )}

      {/* Tab content */}
      {activeTab === "args" && hasArgs && (
        <ToolArgsBlock args={data.tool_args!} size={size} defaultCollapsed={false} />
      )}
      {activeTab === "obs" && hasObs && (
        <ObservationBlock observation={data.observation!} size={size} defaultCollapsed={false} />
      )}

      {hasError && <ErrorBlock error={data.error!} size={size} />}
    </div>
  )

  if (variant === "card") {
    return (
      <Card className="animate-in fade-in-0 slide-in-from-bottom-2 duration-200 border-amber-500/20 py-2">
        <CardContent className="py-0">{content}</CardContent>
      </Card>
    )
  }

  // variant === "inline"
  return (
    <div className="rounded-md border border-border/30 bg-muted/20 px-2.5 py-2">
      {content}
    </div>
  )
}
