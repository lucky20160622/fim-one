"use client"

import { useState, useRef } from "react"
import { Loader2, Upload, CheckCircle2, XCircle, Link } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Textarea } from "@/components/ui/textarea"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog"
import { kbApi } from "@/lib/api"
import type { KBResponse } from "@/types/kb"

interface KBUploadDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  kb: KBResponse | null
  onUploaded: () => void
}

interface UploadItem {
  file: File
  status: "pending" | "uploading" | "done" | "error"
  error?: string
}

interface UrlImportItem {
  url: string
  status: "pending" | "importing" | "done" | "failed"
  error?: string
}

const ACCEPTED_TYPES = ".pdf,.docx,.md,.html,.csv,.txt"

export function KBUploadDialog({
  open,
  onOpenChange,
  kb,
  onUploaded,
}: KBUploadDialogProps) {
  const [tab, setTab] = useState<"file" | "url">("file")

  // File upload state
  const [items, setItems] = useState<UploadItem[]>([])
  const [isUploading, setIsUploading] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // URL import state
  const [urlText, setUrlText] = useState("")
  const [urlItems, setUrlItems] = useState<UrlImportItem[]>([])
  const [isImporting, setIsImporting] = useState(false)

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files
    if (!files) return
    const newItems: UploadItem[] = Array.from(files).map((file) => ({
      file,
      status: "pending" as const,
    }))
    setItems((prev) => [...prev, ...newItems])
    if (fileInputRef.current) fileInputRef.current.value = ""
  }

  const handleUpload = async () => {
    if (!kb || items.length === 0) return
    setIsUploading(true)

    for (let i = 0; i < items.length; i++) {
      if (items[i].status !== "pending") continue

      setItems((prev) =>
        prev.map((item, idx) =>
          idx === i ? { ...item, status: "uploading" } : item
        )
      )

      try {
        await kbApi.uploadDocument(kb.id, items[i].file)
        setItems((prev) =>
          prev.map((item, idx) =>
            idx === i ? { ...item, status: "done" } : item
          )
        )
      } catch (err) {
        const message = err instanceof Error ? err.message : "Upload failed"
        setItems((prev) =>
          prev.map((item, idx) =>
            idx === i ? { ...item, status: "error", error: message } : item
          )
        )
      }
    }

    setIsUploading(false)
    onUploaded()
  }

  const handleImportUrls = async () => {
    if (!kb) return
    const urls = urlText
      .split("\n")
      .map((u) => u.trim())
      .filter((u) => u.length > 0)
      .filter((u, i, arr) => arr.indexOf(u) === i)

    if (urls.length === 0) return
    setIsImporting(true)
    setUrlItems(urls.map((url) => ({ url, status: "importing" as const })))

    try {
      const result = await kbApi.importUrls(kb.id, urls)
      setUrlItems(
        result.results.map((r) => ({
          url: r.url,
          status: r.status === "success" ? "done" : "failed",
          error: r.error,
        }))
      )
      onUploaded()
    } catch (err) {
      const message = err instanceof Error ? err.message : "Import failed"
      setUrlItems(urls.map((url) => ({ url, status: "failed", error: message })))
    }

    setIsImporting(false)
  }

  const handleClose = (openState: boolean) => {
    if (!openState) {
      setItems([])
      setIsUploading(false)
      setUrlText("")
      setUrlItems([])
      setIsImporting(false)
      setTab("file")
    }
    onOpenChange(openState)
  }

  const pendingCount = items.filter((i) => i.status === "pending").length
  const urlLines = urlText
    .split("\n")
    .map((u) => u.trim())
    .filter((u) => u.length > 0)
  const urlCount = [...new Set(urlLines)].length

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Add Documents{kb ? ` to ${kb.name}` : ""}</DialogTitle>
        </DialogHeader>

        <Tabs value={tab} onValueChange={(v) => setTab(v as "file" | "url")}>
          <TabsList className="grid w-full grid-cols-2">
            <TabsTrigger value="file">
              <Upload className="h-3.5 w-3.5 mr-1.5" />
              File Upload
            </TabsTrigger>
            <TabsTrigger value="url">
              <Link className="h-3.5 w-3.5 mr-1.5" />
              URL Import
            </TabsTrigger>
          </TabsList>

          {/* ── File Upload Tab ── */}
          <TabsContent value="file" className="space-y-4 mt-4">
            <div className="flex items-center gap-2">
              <input
                ref={fileInputRef}
                type="file"
                accept={ACCEPTED_TYPES}
                multiple
                onChange={handleFileSelect}
                className="flex-1 text-sm file:mr-2 file:rounded-md file:border-0 file:bg-primary file:px-3 file:py-1.5 file:text-xs file:font-medium file:text-primary-foreground hover:file:bg-primary/90 cursor-pointer"
              />
            </div>

            {items.length > 0 && (
              <div className="max-h-60 overflow-y-auto space-y-2">
                {items.map((item, i) => (
                  <div
                    key={i}
                    className="flex items-center gap-2 text-sm rounded-md border border-border px-3 py-2"
                  >
                    <span className="flex-1 truncate">{item.file.name}</span>
                    {item.status === "pending" && (
                      <Badge variant="secondary" className="text-[10px] px-1.5 py-0 h-5">
                        Pending
                      </Badge>
                    )}
                    {item.status === "uploading" && (
                      <Loader2 className="h-4 w-4 animate-spin text-muted-foreground shrink-0" />
                    )}
                    {item.status === "done" && (
                      <CheckCircle2 className="h-4 w-4 text-emerald-500 shrink-0" />
                    )}
                    {item.status === "error" && (
                      <span title={item.error}>
                        <XCircle className="h-4 w-4 text-destructive shrink-0" />
                      </span>
                    )}
                  </div>
                ))}
              </div>
            )}
          </TabsContent>

          {/* ── URL Import Tab ── */}
          <TabsContent value="url" className="space-y-4 mt-4">
            {urlItems.length === 0 ? (
              <Textarea
                placeholder={"Paste URLs, one per line:\nhttps://docs.example.com\nhttps://blog.example.com/post"}
                value={urlText}
                onChange={(e) => setUrlText(e.target.value)}
                className="min-h-[120px] text-sm font-mono resize-none"
                disabled={isImporting}
              />
            ) : (
              <div className="max-h-60 overflow-y-auto space-y-2">
                {urlItems.map((item, i) => (
                  <div
                    key={i}
                    className="flex items-center gap-2 text-sm rounded-md border border-border px-3 py-2"
                  >
                    <span className="flex-1 truncate text-xs text-muted-foreground">
                      {item.url}
                    </span>
                    {item.status === "importing" && (
                      <Loader2 className="h-4 w-4 animate-spin text-muted-foreground shrink-0" />
                    )}
                    {item.status === "done" && (
                      <CheckCircle2 className="h-4 w-4 text-emerald-500 shrink-0" />
                    )}
                    {item.status === "failed" && (
                      <span title={item.error}>
                        <XCircle className="h-4 w-4 text-destructive shrink-0" />
                      </span>
                    )}
                  </div>
                ))}
              </div>
            )}
            <p className="text-xs text-muted-foreground">
              Pages are fetched via Jina Reader and imported as Markdown documents.
            </p>
          </TabsContent>
        </Tabs>

        <DialogFooter>
          <Button
            variant="ghost"
            onClick={() => handleClose(false)}
            disabled={isUploading || isImporting}
          >
            {isUploading || isImporting ? "Close" : "Cancel"}
          </Button>

          {tab === "file" ? (
            <Button
              onClick={handleUpload}
              disabled={isUploading || pendingCount === 0}
              className="gap-1.5"
            >
              {isUploading ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Upload className="h-4 w-4" />
              )}
              Upload {pendingCount > 0 ? `(${pendingCount})` : ""}
            </Button>
          ) : (
            <Button
              onClick={handleImportUrls}
              disabled={isImporting || urlCount === 0 || urlItems.length > 0}
              className="gap-1.5"
            >
              {isImporting ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Link className="h-4 w-4" />
              )}
              Import {urlCount > 0 && urlItems.length === 0 ? `(${urlCount})` : ""}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
