"use client"

import { useState } from "react"
import { useTranslations, useLocale } from "next-intl"
import { Download, FileText, FileCode, File, Loader2 } from "lucide-react"
import { toast } from "sonner"
import { getErrorMessage } from "@/lib/error-utils"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import { conversationApi } from "@/lib/api"
import { cn } from "@/lib/utils"

type ExportFormat = "md" | "txt" | "docx" | "pdf"

interface ExportDialogProps {
  conversationId: string
  conversationTitle: string
  open: boolean
  onOpenChange: (open: boolean) => void
}

const FORMAT_OPTIONS: { value: ExportFormat; icon: typeof FileCode; labelKey: string; descKey: string }[] = [
  { value: "md", icon: FileCode, labelKey: "exportFormatMd", descKey: "exportFormatMdDesc" },
  { value: "txt", icon: FileText, labelKey: "exportFormatTxt", descKey: "exportFormatTxtDesc" },
  { value: "docx", icon: File, labelKey: "exportFormatDocx", descKey: "exportFormatDocxDesc" },
  { value: "pdf", icon: FileText, labelKey: "exportFormatPdf", descKey: "exportFormatPdfDesc" },
]

export function ExportDialog({ conversationId, open, onOpenChange }: ExportDialogProps) {
  const t = useTranslations("playground")
  const tc = useTranslations("common")
  const tError = useTranslations("errors")
  const locale = useLocale()
  const [format, setFormat] = useState<ExportFormat>("md")
  const [includeDetails, setIncludeDetails] = useState(false)
  const [exporting, setExporting] = useState(false)

  const handleExport = async () => {
    setExporting(true)
    try {
      await conversationApi.export(conversationId, format, includeDetails ? "full" : "summary", locale)
      onOpenChange(false)
    } catch (err) {
      toast.error(getErrorMessage(err, tError))
    } finally {
      setExporting(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{t("exportTitle")}</DialogTitle>
          <DialogDescription>{t("exportDescription")}</DialogDescription>
        </DialogHeader>

        {/* Format selection */}
        <div className="grid gap-2">
          {FORMAT_OPTIONS.map((opt) => {
            const Icon = opt.icon
            const selected = format === opt.value
            return (
              <button
                key={opt.value}
                type="button"
                onClick={() => setFormat(opt.value)}
                className={cn(
                  "flex items-center gap-3 rounded-lg border px-4 py-3 text-left transition-colors",
                  "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary",
                  selected
                    ? "border-primary bg-primary/5"
                    : "border-border hover:bg-muted/50",
                )}
              >
                <Icon className={cn("h-5 w-5 shrink-0", selected ? "text-primary" : "text-muted-foreground")} />
                <div className="min-w-0">
                  <p className={cn("text-sm font-medium", selected ? "text-primary" : "text-foreground")}>
                    {t(opt.labelKey)}
                  </p>
                  <p className="text-xs text-muted-foreground">{t(opt.descKey)}</p>
                </div>
              </button>
            )
          })}
        </div>

        {/* Detail level toggle */}
        <div className="flex items-center justify-between gap-4 rounded-lg border border-border px-4 py-3">
          <div className="space-y-0.5">
            <Label htmlFor="export-details" className="text-sm font-medium cursor-pointer">
              {t("exportIncludeDetails")}
            </Label>
            <p className="text-xs text-muted-foreground">
              {t("exportDetailsDescription")}
            </p>
          </div>
          <Switch
            id="export-details"
            checked={includeDetails}
            onCheckedChange={setIncludeDetails}
          />
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={exporting}>
            {tc("cancel")}
          </Button>
          <Button onClick={handleExport} disabled={exporting}>
            {exporting ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Download className="h-4 w-4" />
            )}
            {t("exportButton")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
