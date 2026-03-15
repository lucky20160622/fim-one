"use client"

import { useCallback } from "react"
import { useRouter } from "next/navigation"
import { useTranslations } from "next-intl"
import { toast } from "sonner"
import {
  BookOpen,
  Boxes,
  FileCode2,
  Globe,
  LayoutTemplate,
  MessageSquare,
} from "lucide-react"
import { workflowApi } from "@/lib/api"
import {
  TemplateGalleryDialog as SharedTemplateGalleryDialog,
} from "@/components/shared/template-gallery-dialog"
import type { WorkflowTemplate } from "@/types/workflow"

// Category icons specific to workflow templates
const workflowCategoryIcons: Record<string, React.ReactNode> = {
  basic: <MessageSquare className="h-5 w-5" />,
  intermediate: <Boxes className="h-5 w-5" />,
  advanced: <LayoutTemplate className="h-5 w-5" />,
  ai: <BookOpen className="h-5 w-5" />,
  integration: <Globe className="h-5 w-5" />,
  data: <FileCode2 className="h-5 w-5" />,
}

interface TemplateGalleryDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function TemplateGalleryDialog({
  open,
  onOpenChange,
}: TemplateGalleryDialogProps) {
  const t = useTranslations("workflows")
  const router = useRouter()

  const fetchTemplates = useCallback(
    () => workflowApi.getTemplates(),
    [],
  )

  const handleCreate = useCallback(
    async (templateId: string) => {
      const workflow = await workflowApi.createFromTemplate(templateId)
      toast.success(t("templateCreateSuccess"))
      router.push(`/workflows/${workflow.id}`)
    },
    [t, router],
  )

  const categoryLabels: Record<string, string> = {
    basic: t("templateCategory_basic"),
    intermediate: t("templateCategory_intermediate"),
    advanced: t("templateCategory_advanced"),
    ai: t("templateCategory_ai"),
    integration: t("templateCategory_integration"),
    data: t("templateCategory_data"),
  }

  return (
    <SharedTemplateGalleryDialog<WorkflowTemplate>
      open={open}
      onOpenChange={onOpenChange}
      title={t("galleryTitle")}
      description={t("galleryDescription")}
      fetchTemplates={fetchTemplates}
      onCreateFromTemplate={handleCreate}
      categoryLabels={categoryLabels}
      categoryIcons={workflowCategoryIcons}
      renderExtra={(tmpl) => {
        const nodeCount = tmpl.blueprint?.nodes?.length ?? 0
        if (nodeCount <= 0) return null
        return (
          <span className="text-[10px] text-muted-foreground">
            {t("nodeCount", { count: nodeCount })}
          </span>
        )
      }}
      selectHint={t("gallerySelectHint")}
      emptyText={t("galleryEmpty")}
      createFailedText={t("templateCreateFailed")}
    />
  )
}
