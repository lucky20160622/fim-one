"use client"

import { useState, useEffect, useCallback, Suspense } from "react"
import { useParams, useRouter, useSearchParams } from "next/navigation"
import Link from "next/link"
import { useTranslations } from "next-intl"
import { ArrowLeft, BookOpen, Loader2, Code2, CheckCircle2, Plus } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog"
import { cn } from "@/lib/utils"
import { useAuth } from "@/contexts/auth-context"
import { skillApi } from "@/lib/api"
import { ResourcePickerDialog } from "@/components/skills/resource-picker-dialog"
import { ResourceRefsBadges } from "@/components/skills/resource-refs-badges"
import { MentionTextarea } from "@/components/skills/mention-textarea"
import type { SkillResponse, ResourceRef } from "@/types/skill"

type TabKey = "content" | "script" | "settings"

function SkillEditorContent() {
  const t = useTranslations("skills")
  const tc = useTranslations("common")
  const params = useParams()
  const router = useRouter()
  const searchParams = useSearchParams()
  const { user, isLoading: authLoading } = useAuth()

  const id = params.id as string
  const activeTab = (searchParams.get("tab") as TabKey) || "content"

  const [skill, setSkill] = useState<SkillResponse | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [showLeaveDialog, setShowLeaveDialog] = useState(false)

  // Form state
  const [name, setName] = useState("")
  const [description, setDescription] = useState("")
  const [content, setContent] = useState("")
  const [script, setScript] = useState("")
  const [scriptType, setScriptType] = useState<"python" | "shell" | "__none__">("__none__")
  const [isActive, setIsActive] = useState(true)
  const [resourceRefs, setResourceRefs] = useState<ResourceRef[]>([])
  const [showResourcePicker, setShowResourcePicker] = useState(false)

  // Compute dirty state
  const isDirty = skill
    ? name !== skill.name ||
      description !== (skill.description || "") ||
      content !== skill.content ||
      script !== (skill.script || "") ||
      (scriptType === "__none__" ? null : scriptType) !== skill.script_type ||
      isActive !== skill.is_active ||
      JSON.stringify(resourceRefs) !== JSON.stringify(skill.resource_refs || [])
    : false

  // Warn on browser refresh / tab close
  useEffect(() => {
    if (!isDirty) return
    const handler = (e: BeforeUnloadEvent) => { e.preventDefault() }
    window.addEventListener("beforeunload", handler)
    return () => window.removeEventListener("beforeunload", handler)
  }, [isDirty])

  // Auth guard
  useEffect(() => {
    if (!authLoading && !user) {
      router.replace("/login")
    }
  }, [authLoading, user, router])

  const loadSkill = useCallback(async () => {
    try {
      setIsLoading(true)
      const data = await skillApi.get(id)
      setSkill(data)
      setName(data.name)
      setDescription(data.description || "")
      setContent(data.content)
      setScript(data.script || "")
      setScriptType(data.script_type || "__none__")
      setIsActive(data.is_active)
      setResourceRefs(data.resource_refs || [])
    } catch (err) {
      console.error("Failed to load skill:", err)
      router.replace("/skills")
    } finally {
      setIsLoading(false)
    }
  }, [id, router])

  useEffect(() => {
    if (user) loadSkill()
  }, [user, loadSkill])

  const handleSave = async () => {
    if (!skill) return
    const trimmedName = name.trim()
    if (!trimmedName) return

    setIsSubmitting(true)
    try {
      const updated = await skillApi.update(skill.id, {
        name: trimmedName,
        description: description.trim() || null,
        content,
        script: script.trim() || null,
        script_type: scriptType === "__none__" ? null : scriptType,
        is_active: isActive,
        resource_refs: resourceRefs.length > 0 ? resourceRefs : null,
      })
      setSkill(updated)
      setName(updated.name)
      setDescription(updated.description || "")
      setContent(updated.content)
      setScript(updated.script || "")
      setScriptType(updated.script_type || "__none__")
      setIsActive(updated.is_active)
      setResourceRefs(updated.resource_refs || [])
      toast.success(t("skillSaved"))
    } catch (err) {
      console.error("Failed to save skill:", err)
      toast.error(t("skillSaveFailed"))
    } finally {
      setIsSubmitting(false)
    }
  }

  if (authLoading || !user) return null

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    )
  }

  const tabs: { key: TabKey; label: string }[] = [
    { key: "content", label: t("tabContent") },
    { key: "script", label: t("tabScript") },
    { key: "settings", label: t("tabSettings") },
  ]

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Top bar */}
      <div className="flex items-center gap-3 px-4 py-3 border-b border-border/40 shrink-0">
        <Tooltip>
          <TooltipTrigger asChild>
            {isDirty ? (
              <Button
                variant="ghost"
                size="icon-xs"
                onClick={() => setShowLeaveDialog(true)}
              >
                <ArrowLeft className="h-4 w-4" />
              </Button>
            ) : (
              <Button variant="ghost" size="icon-xs" asChild>
                <Link href="/skills">
                  <ArrowLeft className="h-4 w-4" />
                </Link>
              </Button>
            )}
          </TooltipTrigger>
          <TooltipContent side="right" sideOffset={5}>{t("backToList")}</TooltipContent>
        </Tooltip>
        <h1 className="text-sm font-semibold text-foreground truncate flex items-center gap-2">
          <BookOpen className="h-4 w-4 shrink-0" />
          {skill?.name || t("newSkill")}
        </h1>
        <div className="flex-1" />
        <Button
          size="sm"
          onClick={handleSave}
          disabled={isSubmitting || !name.trim() || !isDirty}
        >
          {isSubmitting && <Loader2 className="h-4 w-4 animate-spin" />}
          {tc("save")}
        </Button>
      </div>

      {/* Tab navigation */}
      <div className="flex items-center gap-1 px-4 pt-2 border-b border-border/40 shrink-0">
        {tabs.map((tab) => {
          if (tab.key === "script") {
            // Script tab is coming-soon: still navigable but visually de-emphasized
            return (
              <Link
                key="script"
                href={`/skills/${id}?tab=script`}
                className={cn(
                  "px-3 py-1.5 text-sm font-medium transition-colors rounded-t-md border-b-2 -mb-px flex items-center gap-1.5",
                  activeTab === "script"
                    ? "border-primary text-foreground"
                    : "border-transparent text-muted-foreground hover:text-foreground hover:border-border",
                )}
              >
                {t("tabScript")}
                <span className="text-[10px] font-normal px-1 py-0.5 rounded bg-muted text-muted-foreground leading-none">soon</span>
              </Link>
            )
          }
          return (
            <Link
              key={tab.key}
              href={tab.key === "content" ? `/skills/${id}` : `/skills/${id}?tab=${tab.key}`}
              className={cn(
                "px-3 py-1.5 text-sm font-medium transition-colors rounded-t-md border-b-2 -mb-px",
                activeTab === tab.key
                  ? "border-primary text-foreground"
                  : "border-transparent text-muted-foreground hover:text-foreground hover:border-border",
              )}
            >
              {tab.label}
            </Link>
          )
        })}
      </div>

      {/* Tab content */}
      <div className="flex-1 overflow-y-auto p-6">
        <div className="max-w-2xl space-y-6">
          {activeTab === "content" && (
            <>
              {/* Name */}
              <div className="space-y-2">
                <Label htmlFor="skill-name">
                  {t("fieldName")} <span className="text-destructive">*</span>
                </Label>
                <Input
                  id="skill-name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder={t("fieldNamePlaceholder")}
                  required
                />
              </div>

              {/* Description */}
              <div className="space-y-2">
                <Label htmlFor="skill-description">{t("fieldDescription")}</Label>
                <p className="text-xs text-muted-foreground">{t("fieldDescriptionHint")}</p>
                <Input
                  id="skill-description"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder={t("fieldDescriptionPlaceholder")}
                />
              </div>

              {/* Content */}
              <div className="space-y-2">
                <Label htmlFor="skill-content">{t("fieldContent")}</Label>
                <p className="text-xs text-muted-foreground">{t("fieldContentHint")}</p>
                <MentionTextarea
                  id="skill-content"
                  value={content}
                  onChange={setContent}
                  placeholder={t("fieldContentPlaceholder")}
                  className="min-h-[300px] resize-y font-mono text-sm"
                  resourceRefs={resourceRefs}
                />
              </div>

              {/* Resource References */}
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <div>
                    <Label>{t("resourceRefs")}</Label>
                    <p className="text-xs text-muted-foreground mt-0.5">{t("resourceRefsHint")}</p>
                  </div>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="gap-1.5 shrink-0"
                    onClick={() => setShowResourcePicker(true)}
                  >
                    <Plus className="h-3.5 w-3.5" />
                    {t("addResource")}
                  </Button>
                </div>
                <ResourceRefsBadges
                  refs={resourceRefs}
                  onRemove={(index) =>
                    setResourceRefs((prev) => prev.filter((_, i) => i !== index))
                  }
                  onUpdateAlias={(index, newAlias) =>
                    setResourceRefs((prev) =>
                      prev.map((ref, i) =>
                        i === index ? { ...ref, alias: newAlias } : ref,
                      ),
                    )
                  }
                />
              </div>
            </>
          )}

          {activeTab === "script" && (
            <div className="flex flex-col items-center justify-center py-16 text-center gap-4">
              <div className="rounded-full bg-muted p-4">
                <Code2 className="h-8 w-8 text-muted-foreground" />
              </div>
              <div className="space-y-1.5 max-w-sm">
                <h3 className="text-sm font-semibold">{t("scriptComingSoonTitle")}</h3>
                <p className="text-sm text-muted-foreground">{t("scriptComingSoonDescription")}</p>
              </div>
              <div className="flex flex-col gap-1.5 text-sm text-muted-foreground text-left w-full max-w-xs mt-2">
                {(t.raw("scriptComingSoonFeatures") as string[]).map((f: string, i: number) => (
                  <div key={i} className="flex items-center gap-2">
                    <CheckCircle2 className="h-3.5 w-3.5 text-primary shrink-0" />
                    <span>{f}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {activeTab === "settings" && (
            <>
              <div className="flex items-center justify-between rounded-md border border-border px-3 py-2.5">
                <div>
                  <Label htmlFor="skill-active" className="text-sm font-medium cursor-pointer">
                    {tc("active")}
                  </Label>
                  <p className="text-xs text-muted-foreground mt-0.5">{t("settingActiveHint")}</p>
                </div>
                <Switch
                  id="skill-active"
                  checked={isActive}
                  onCheckedChange={setIsActive}
                />
              </div>
            </>
          )}
        </div>
      </div>

      {/* Resource picker dialog */}
      <ResourcePickerDialog
        open={showResourcePicker}
        onOpenChange={setShowResourcePicker}
        existingRefs={resourceRefs}
        onAdd={(ref) =>
          setResourceRefs((prev) => [...prev, ref])
        }
      />

      {/* Unsaved changes dialog -- sibling of the main content, not nested */}
      <AlertDialog open={showLeaveDialog} onOpenChange={setShowLeaveDialog}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t("unsavedChangesTitle")}</AlertDialogTitle>
            <AlertDialogDescription>
              {t("unsavedChangesDescription")}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("stay")}</AlertDialogCancel>
            <AlertDialogAction onClick={() => router.push("/skills")}>
              {t("discardAndLeave")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}

export default function SkillEditorPage() {
  return (
    <Suspense fallback={
      <div className="flex items-center justify-center h-full">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    }>
      <SkillEditorContent />
    </Suspense>
  )
}
