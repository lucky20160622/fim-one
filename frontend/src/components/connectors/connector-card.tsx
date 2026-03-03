"use client"

import { Trash2, Globe } from "lucide-react"
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
}: ConnectorCardProps) {
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => onEdit(connector)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault()
          onEdit(connector)
        }
      }}
      className="flex flex-col rounded-lg border border-border bg-card p-4 transition-colors hover:border-border/80 hover:bg-accent/5 cursor-pointer"
    >
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
      <div className="flex items-center -ml-1">
        <div className="flex-1" />
        <Button
          variant="ghost"
          size="icon-xs"
          onClick={(e) => {
            e.stopPropagation()
            onDelete(connector.id)
          }}
          className="text-muted-foreground hover:text-destructive"
          title="Delete"
        >
          <Trash2 className="h-3.5 w-3.5" />
        </Button>
      </div>
    </div>
  )
}
