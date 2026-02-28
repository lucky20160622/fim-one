"use client"

import { useState, useEffect } from "react"
import { Loader2, FilePlus } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetFooter,
} from "@/components/ui/sheet"
import { kbApi } from "@/lib/api"

interface MdCreateDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  kbId: string
  onCreated: () => void
}

export function MdCreateDialog({
  open,
  onOpenChange,
  kbId,
  onCreated,
}: MdCreateDialogProps) {
  const [filename, setFilename] = useState("")
  const [content, setContent] = useState("")
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (open) {
      setFilename("")
      setContent("")
      setError(null)
    }
  }, [open])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    const trimmedName = filename.trim()
    const trimmedContent = content.trim()

    if (!trimmedName || !trimmedContent) return

    // Ensure .md extension
    const finalName = trimmedName.endsWith(".md")
      ? trimmedName
      : `${trimmedName}.md`

    setIsSubmitting(true)
    setError(null)
    try {
      await kbApi.createDocument(kbId, {
        filename: finalName,
        content: trimmedContent,
      })
      onOpenChange(false)
      onCreated()
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to create document"
      setError(message)
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="sm:max-w-xl w-full flex flex-col">
        <SheetHeader>
          <SheetTitle>New Markdown Document</SheetTitle>
        </SheetHeader>

        <form onSubmit={handleSubmit} className="flex-1 flex flex-col gap-4 overflow-hidden">
          <div className="space-y-1.5">
            <label htmlFor="md-filename" className="text-sm font-medium">
              Filename <span className="text-destructive">*</span>
            </label>
            <Input
              id="md-filename"
              value={filename}
              onChange={(e) => setFilename(e.target.value)}
              placeholder="notes.md"
              required
              disabled={isSubmitting}
            />
            <p className="text-xs text-muted-foreground">
              .md extension will be added automatically if omitted.
            </p>
          </div>

          <div className="flex-1 flex flex-col gap-1.5 min-h-0">
            <label htmlFor="md-content" className="text-sm font-medium">
              Content <span className="text-destructive">*</span>
            </label>
            <Textarea
              id="md-content"
              value={content}
              onChange={(e) => setContent(e.target.value)}
              placeholder="# My Document&#10;&#10;Write your markdown content here..."
              className="font-mono text-sm flex-1 resize-none min-h-0"
              required
              disabled={isSubmitting}
            />
          </div>

          {error && (
            <p className="text-sm text-destructive">{error}</p>
          )}

          <SheetFooter>
            <Button
              type="button"
              variant="ghost"
              onClick={() => onOpenChange(false)}
              disabled={isSubmitting}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={isSubmitting || !filename.trim() || !content.trim()}
              className="gap-1.5"
            >
              {isSubmitting ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <FilePlus className="h-4 w-4" />
              )}
              Create
            </Button>
          </SheetFooter>
        </form>
      </SheetContent>
    </Sheet>
  )
}
