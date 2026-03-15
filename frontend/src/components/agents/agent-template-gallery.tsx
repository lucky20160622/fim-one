"use client"

import { useCallback } from "react"
import { useRouter } from "next/navigation"
import { useTranslations } from "next-intl"
import { toast } from "sonner"
import { agentApi } from "@/lib/api"
import {
  TemplateGalleryDialog as SharedTemplateGalleryDialog,
} from "@/components/shared/template-gallery-dialog"
import type { AgentTemplate } from "@/types/agent"

interface AgentTemplateGalleryProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function AgentTemplateGallery({
  open,
  onOpenChange,
}: AgentTemplateGalleryProps) {
  const t = useTranslations("agents")
  const router = useRouter()

  const fetchTemplates = useCallback(
    () => agentApi.getTemplates(),
    [],
  )

  const handleCreate = useCallback(
    async (templateId: string) => {
      const agent = await agentApi.createFromTemplate(templateId)
      toast.success(t("agentCreated"))
      router.push(`/agents/${agent.id}`)
    },
    [t, router],
  )

  const categoryLabels: Record<string, string> = {
    basic: t("templateCategory_basic"),
    advanced: t("templateCategory_advanced"),
    ai: t("templateCategory_ai"),
    data: t("templateCategory_data"),
  }

  return (
    <SharedTemplateGalleryDialog<AgentTemplate>
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
