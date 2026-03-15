"use client"

import { useCallback } from "react"
import { useTranslations } from "next-intl"
import { toast } from "sonner"
import { skillApi } from "@/lib/api"
import {
  TemplateGalleryDialog as SharedTemplateGalleryDialog,
} from "@/components/shared/template-gallery-dialog"
import type { SkillTemplate } from "@/types/skill"

interface SkillTemplateGalleryProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onCreated?: () => void
}

export function SkillTemplateGallery({
  open,
  onOpenChange,
  onCreated,
}: SkillTemplateGalleryProps) {
  const t = useTranslations("skills")

  const fetchTemplates = useCallback(
    () => skillApi.getTemplates(),
    [],
  )

  const handleCreate = useCallback(
    async (templateId: string) => {
      await skillApi.createFromTemplate(templateId)
      toast.success(t("skillCreated"))
      onCreated?.()
    },
    [t, onCreated],
  )

  const categoryLabels: Record<string, string> = {
    text: t("templateCategory_text"),
    data: t("templateCategory_data"),
    writing: t("templateCategory_writing"),
    code: t("templateCategory_code"),
    ai: t("templateCategory_ai"),
  }

  return (
    <SharedTemplateGalleryDialog<SkillTemplate>
      open={open}
      onOpenChange={onOpenChange}
      title={t("templateGalleryTitle")}
      description={t("templateGalleryDescription")}
      fetchTemplates={fetchTemplates}
      onCreateFromTemplate={handleCreate}
      categoryLabels={categoryLabels}
      selectHint={t("templateSelectHint")}
      emptyText={t("templateEmpty")}
      createFailedText={t("templateCreateFailed")}
    />
  )
}
