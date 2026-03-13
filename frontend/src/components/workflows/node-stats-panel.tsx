"use client"

import { useState, useEffect } from "react"
import { useTranslations } from "next-intl"
import {
  Loader2,
  Activity,
  BarChart3,
  CheckCircle2,
  XCircle,
  SkipForward,
} from "lucide-react"
import { toast } from "sonner"
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet"
import { ScrollArea } from "@/components/ui/scroll-area"
import { cn } from "@/lib/utils"
import { fmtDuration } from "@/lib/utils"
import { workflowApi } from "@/lib/api"
import type { NodeStatEntry, WorkflowNodeType } from "@/types/workflow"

interface NodeStatsPanelProps {
  workflowId: string
  open: boolean
  onOpenChange: (open: boolean) => void
  /** Map of nodeId → node type for display labels */
  nodeTypeMap: Record<string, WorkflowNodeType>
}

function formatMs(ms: number | null): string {
  if (ms === null || ms === 0) return "—"
  return fmtDuration(ms / 1000)
}

function getSuccessColor(rate: number | null): string {
  if (rate === null) return "bg-muted"
  if (rate >= 80) return "bg-emerald-500"
  if (rate >= 50) return "bg-amber-500"
  return "bg-red-500"
}

function getSuccessTextColor(rate: number | null): string {
  if (rate === null) return "text-muted-foreground"
  if (rate >= 80) return "text-emerald-600 dark:text-emerald-400"
  if (rate >= 50) return "text-amber-600 dark:text-amber-400"
  return "text-red-600 dark:text-red-400"
}

export function NodeStatsPanel({
  workflowId,
  open,
  onOpenChange,
  nodeTypeMap,
}: NodeStatsPanelProps) {
  const t = useTranslations("workflows")

  const [nodes, setNodes] = useState<NodeStatEntry[]>([])
  const [runsAnalyzed, setRunsAnalyzed] = useState(0)
  const [isLoading, setIsLoading] = useState(false)

  useEffect(() => {
    if (!open || !workflowId) return
    let cancelled = false
    setIsLoading(true)
    workflowApi
      .getNodeStats(workflowId)
      .then((data) => {
        if (!cancelled) {
          setNodes(data.nodes)
          setRunsAnalyzed(data.runs_analyzed)
        }
      })
      .catch(() => {
        if (!cancelled) toast.error(t("historyLoadFailed"))
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [open, workflowId, t])

  // Sort by success rate ascending (worst first)
  const sortedNodes = [...nodes].sort((a, b) => {
    const aRate = a.success_rate ?? 100
    const bRate = b.success_rate ?? 100
    return aRate - bRate
  })

  const hasData = sortedNodes.length > 0

  const getNodeLabel = (nodeId: string): string => {
    const nodeType = nodeTypeMap[nodeId]
    if (nodeType) {
      return t(`nodeType_${nodeType}` as Parameters<typeof t>[0])
    }
    return nodeId
  }

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="sm:max-w-sm p-0 flex flex-col">
        <SheetHeader className="px-6 pt-6 pb-3 border-b border-border/40 shrink-0">
          <SheetTitle className="text-sm flex items-center gap-2">
            <BarChart3 className="h-4 w-4" />
            {t("nodeStatsTitle")}
          </SheetTitle>
          <SheetDescription className="text-xs">
            {hasData
              ? t("nodeStatsRunsAnalyzed", { count: runsAnalyzed })
              : t("nodeStatsEmpty")}
          </SheetDescription>
        </SheetHeader>

        <ScrollArea className="flex-1 min-h-0">
          {isLoading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            </div>
          ) : !hasData ? (
            <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
              <Activity className="h-8 w-8 mb-2 opacity-40" />
              <p className="text-sm">{t("nodeStatsEmpty")}</p>
            </div>
          ) : (
            <div className="p-4 space-y-2">
              {sortedNodes.map((entry) => (
                <div
                  key={entry.node_id}
                  className="rounded-md border border-border p-3 space-y-2"
                >
                  {/* Node header */}
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-1.5 min-w-0">
                      <span className="text-xs font-medium text-foreground truncate">
                        {getNodeLabel(entry.node_id)}
                      </span>
                      {nodeTypeMap[entry.node_id] && (
                        <span className="text-[10px] text-muted-foreground shrink-0">
                          ({entry.node_id})
                        </span>
                      )}
                    </div>
                    <span
                      className={cn(
                        "text-xs font-semibold tabular-nums",
                        getSuccessTextColor(entry.success_rate),
                      )}
                    >
                      {entry.success_rate !== null
                        ? `${entry.success_rate}%`
                        : "—"}
                    </span>
                  </div>

                  {/* Success rate bar */}
                  <div className="h-1.5 w-full rounded-full bg-muted">
                    <div
                      className={cn(
                        "h-full rounded-full transition-all duration-500",
                        getSuccessColor(entry.success_rate),
                      )}
                      style={{
                        width: `${Math.min(entry.success_rate ?? 0, 100)}%`,
                      }}
                    />
                  </div>

                  {/* Counts row */}
                  <div className="flex items-center gap-3 text-[10px]">
                    <span className="flex items-center gap-1 text-muted-foreground">
                      <CheckCircle2 className="h-3 w-3 text-green-500" />
                      {entry.completed}
                    </span>
                    <span className="flex items-center gap-1 text-muted-foreground">
                      <XCircle className="h-3 w-3 text-red-500" />
                      {entry.failed}
                    </span>
                    <span className="flex items-center gap-1 text-muted-foreground">
                      <SkipForward className="h-3 w-3 text-zinc-400" />
                      {entry.skipped}
                    </span>
                    <span className="text-muted-foreground ml-auto tabular-nums">
                      {entry.total_runs} {t("nodeStatsTotalRuns").toLowerCase()}
                    </span>
                  </div>

                  {/* Duration row */}
                  {entry.avg_duration_ms !== null && (
                    <div className="flex items-center gap-2 text-[10px] text-muted-foreground">
                      <span>
                        {t("nodeStatsAvg")}: <span className="tabular-nums font-medium text-foreground">{formatMs(entry.avg_duration_ms)}</span>
                      </span>
                      <span className="text-border">|</span>
                      <span>
                        {t("nodeStatsMin")}: <span className="tabular-nums">{formatMs(entry.min_duration_ms)}</span>
                      </span>
                      <span className="text-border">|</span>
                      <span>
                        {t("nodeStatsMax")}: <span className="tabular-nums">{formatMs(entry.max_duration_ms)}</span>
                      </span>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </ScrollArea>
      </SheetContent>
    </Sheet>
  )
}
