"use client"

import { useState } from "react"
import { Loader2, Check, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"

interface ChunkEditorProps {
  content: string
  maxLength?: number
  onSave: (content: string) => Promise<void>
  onCancel: () => void
}

export function ChunkEditor({ content, maxLength, onSave, onCancel }: ChunkEditorProps) {
  const [value, setValue] = useState(content)
  const [isSaving, setIsSaving] = useState(false)

  const handleSave = async () => {
    const trimmed = value.trim()
    if (!trimmed || trimmed === content) {
      onCancel()
      return
    }
    setIsSaving(true)
    try {
      await onSave(trimmed)
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <div className="space-y-2">
      <Textarea
        value={value}
        onChange={(e) => setValue(e.target.value)}
        maxLength={maxLength}
        rows={6}
        className="text-sm font-mono"
        disabled={isSaving}
        autoFocus
      />
      <div className="flex items-center gap-1.5 justify-end">
        {maxLength && (
          <span className={`text-[10px] tabular-nums mr-auto ${value.length > maxLength * 0.9 ? "text-amber-500" : "text-muted-foreground"}`}>
            {value.length}/{maxLength}
          </span>
        )}
        <Button
          variant="ghost"
          size="sm"
          onClick={onCancel}
          disabled={isSaving}
          className="h-7 px-2 text-xs"
        >
          <X className="h-3.5 w-3.5 mr-1" />
          Cancel
        </Button>
        <Button
          size="sm"
          onClick={handleSave}
          disabled={isSaving || !value.trim()}
          className="h-7 px-2 text-xs"
        >
          {isSaving ? (
            <Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" />
          ) : (
            <Check className="h-3.5 w-3.5 mr-1" />
          )}
          Save
        </Button>
      </div>
    </div>
  )
}
