"use client"

import { useCallback } from "react"
import { useRouter } from "next/navigation"
import { useTranslations } from "next-intl"
import { toast } from "sonner"
import { connectorApi } from "@/lib/api"
import {
  TemplateGalleryDialog as SharedTemplateGalleryDialog,
} from "@/components/shared/template-gallery-dialog"
import type { ConnectorTemplate } from "@/types/connector"

interface ConnectorTemplateGalleryProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function ConnectorTemplateGallery({
  open,
  onOpenChange,
}: ConnectorTemplateGalleryProps) {
  const t = useTranslations("connectors")
  const router = useRouter()

  const fetchTemplates = useCallback(
    () => connectorApi.getTemplates(),
    [],
  )

  const handleCreate = useCallback(
    async (templateId: string) => {
      const connector = await connectorApi.createFromTemplate(templateId)
      toast.success(t("connectorCreated"))
      router.push(`/connectors/${connector.id}`)
    },
    [t, router],
  )

  const categoryLabels: Record<string, string> = {
    api: t("templateCategory_api"),
    database: t("templateCategory_database"),
  }

  return (
    <SharedTemplateGalleryDialog<ConnectorTemplate>
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
