"use client"

import {
  AlertTriangle,
  CheckCircle2,
  GitBranch,
  Loader2,
  XCircle,
} from "lucide-react"
import { useTranslations } from "next-intl"
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Badge } from "@/components/ui/badge"
import type { WorkflowValidateResponse } from "@/types/workflow"

interface ValidationPanelProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  isLoading: boolean
  result: WorkflowValidateResponse | null
  onNodeClick?: (nodeId: string) => void
}

export function ValidationPanel({
  open,
  onOpenChange,
  isLoading,
  result,
  onNodeClick,
}: ValidationPanelProps) {
  const t = useTranslations("workflows")

  const hasErrors = result ? result.errors.length > 0 : false
  const hasWarnings = result ? result.warnings.length > 0 : false

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="sm:max-w-sm p-0 flex flex-col">
        <SheetHeader className="px-6 pt-6 pb-3 border-b border-border/40 shrink-0">
          <SheetTitle className="text-sm flex items-center gap-2">
            <CheckCircle2 className="h-4 w-4" />
            {t("validateTitle")}
          </SheetTitle>
          <SheetDescription className="text-xs">
            {t("validateDescription")}
          </SheetDescription>
        </SheetHeader>

        <ScrollArea className="flex-1 min-h-0">
          {isLoading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            </div>
          ) : !result ? (
            <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
              <CheckCircle2 className="h-8 w-8 mb-2 opacity-40" />
              <p className="text-sm">{t("validateNoResults")}</p>
            </div>
          ) : (
            <div className="p-4 space-y-4">
              {/* Overall status */}
              <div className="rounded-md border border-border p-3">
                <div className="flex items-center gap-2">
                  {result.valid ? (
                    <CheckCircle2 className="h-4 w-4 text-emerald-500 shrink-0" />
                  ) : (
                    <XCircle className="h-4 w-4 text-destructive shrink-0" />
                  )}
                  <span className="text-sm font-medium flex-1">
                    {result.valid
                      ? t("validationValid")
                      : t("validationInvalid")}
                  </span>
                </div>
              </div>

              {/* Stats */}
              <div className="flex items-center gap-2">
                <Badge variant="secondary" className="text-[10px]">
                  {t("validateNodeCount", { count: result.node_count })}
                </Badge>
                <Badge variant="secondary" className="text-[10px]">
                  {t("validateEdgeCount", { count: result.edge_count })}
                </Badge>
              </div>

              {/* Errors */}
              {hasErrors && (
                <div className="space-y-1.5">
                  <div className="flex items-center gap-1.5">
                    <XCircle className="h-3.5 w-3.5 text-destructive" />
                    <span className="text-xs font-medium text-destructive">
                      {t("validateErrors", { count: result.errors.length })}
                    </span>
                  </div>
                  <div className="rounded-md border border-destructive/30 overflow-hidden">
                    {result.errors.map((err, i) => (
                      <div
                        key={i}
                        className="px-3 py-2 text-xs text-destructive border-b border-destructive/10 last:border-0 bg-destructive/5"
                      >
                        {err}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Warnings */}
              {hasWarnings && (
                <div className="space-y-1.5">
                  <div className="flex items-center gap-1.5">
                    <AlertTriangle className="h-3.5 w-3.5 text-amber-500" />
                    <span className="text-xs font-medium text-amber-600 dark:text-amber-400">
                      {t("validationWarnings", { count: result.warnings.length })}
                    </span>
                  </div>
                  <div className="rounded-md border border-amber-400/30 overflow-hidden">
                    {result.warnings.map((w, i) => (
                      <div
                        key={`${w.node_id ?? "global"}-${w.code}-${i}`}
                        className="px-3 py-2 text-xs border-b border-amber-400/10 last:border-0 bg-amber-500/5"
                      >
                        <p className="text-foreground">{w.message}</p>
                        {w.node_id && (
                          <button
                            className="text-muted-foreground mt-0.5 hover:text-foreground transition-colors underline underline-offset-2"
                            onClick={() => onNodeClick?.(w.node_id!)}
                          >
                            {w.node_id}
                          </button>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* No errors or warnings */}
              {!hasErrors && !hasWarnings && result.valid && (
                <div className="flex flex-col items-center py-4 text-emerald-600 dark:text-emerald-400">
                  <CheckCircle2 className="h-6 w-6 mb-1.5" />
                  <p className="text-xs">{t("validateAllClear")}</p>
                </div>
              )}

              {/* Topology order */}
              {result.topology_order.length > 0 && (
                <div className="space-y-1.5">
                  <div className="flex items-center gap-1.5">
                    <GitBranch className="h-3.5 w-3.5 text-muted-foreground" />
                    <span className="text-xs font-medium text-muted-foreground">
                      {t("validateTopologyOrder")}
                    </span>
                  </div>
                  <div className="rounded-md border border-border p-2">
                    <div className="flex flex-wrap gap-1">
                      {result.topology_order.map((nodeId, i) => (
                        <Badge
                          key={nodeId}
                          variant="outline"
                          className="text-[10px] cursor-pointer hover:bg-accent transition-colors"
                          onClick={() => onNodeClick?.(nodeId)}
                        >
                          {i + 1}. {nodeId}
                        </Badge>
                      ))}
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}
        </ScrollArea>
      </SheetContent>
    </Sheet>
  )
}
