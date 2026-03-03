"use client"

import { Pencil, Trash2, Zap, Globe } from "lucide-react"
import { Button } from "@/components/ui/button"
import type { ConnectorResponse } from "@/types/connector"

interface ConnectorCardProps {
  connector: ConnectorResponse
  onEdit: (connector: ConnectorResponse) => void
  onDelete: (id: string) => void
  onManageActions: (connector: ConnectorResponse) => void
}

const AUTH_LABELS: Record<string, string> = {
  none: "No Auth",
  bearer: "Bearer",
  api_key: "API Key",
  basic: "Basic",
  oauth2: "OAuth2",
}

export function ConnectorCard({
  connector,
  onEdit,
  onDelete,
  onManageActions,
}: ConnectorCardProps) {
  return (
    <div className="flex flex-col rounded-lg border border-border bg-card p-4 transition-colors hover:border-border/80 hover:bg-accent/5">
      {/* Header: name + badges */}
      <div className="flex items-start gap-2 mb-2">
        <h3 className="flex-1 min-w-0 text-sm font-medium truncate text-card-foreground">
          {connector.name}
        </h3>
        <span className="shrink-0 text-[10px] px-1.5 py-0 h-5 inline-flex items-center rounded-full bg-amber-500/10 text-amber-500 font-medium">
          {connector.type === "api" ? "API" : "Database"}
        </span>
      </div>

      {/* Auth type */}
      <p className="text-xs text-muted-foreground mb-1">
        {AUTH_LABELS[connector.auth_type] || connector.auth_type}
        {" \u00B7 "}
        {connector.actions.length} action{connector.actions.length !== 1 ? "s" : ""}
      </p>

      {/* Base URL */}
      <p className="text-xs text-muted-foreground truncate mb-1" title={connector.base_url}>
        <Globe className="inline h-3 w-3 mr-1 -mt-0.5" />
        {connector.base_url}
      </p>

      {/* Description */}
      <p className="flex-1 text-xs text-muted-foreground line-clamp-2 mb-3">
        {connector.description || "No description"}
      </p>

      {/* Action buttons */}
      <div className="flex items-center gap-1 -ml-1">
        <Button
          variant="ghost"
          size="icon-xs"
          onClick={() => onManageActions(connector)}
          className="text-muted-foreground hover:text-foreground"
          title="Manage Actions"
        >
          <Zap className="h-3.5 w-3.5" />
        </Button>
        <Button
          variant="ghost"
          size="icon-xs"
          onClick={() => onEdit(connector)}
          className="text-muted-foreground hover:text-foreground"
          title="Edit"
        >
          <Pencil className="h-3.5 w-3.5" />
        </Button>
        <div className="flex-1" />
        <Button
          variant="ghost"
          size="icon-xs"
          onClick={() => onDelete(connector.id)}
          className="text-muted-foreground hover:text-destructive"
          title="Delete"
        >
          <Trash2 className="h-3.5 w-3.5" />
        </Button>
      </div>
    </div>
  )
}
