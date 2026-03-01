"use client"

import { useState, useEffect } from "react"
import { Loader2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog"
import type { ConnectorCreate, ConnectorUpdate, ConnectorResponse } from "@/types/connector"

interface ConnectorFormDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  connector: ConnectorResponse | null // null = create mode
  onSubmit: (data: ConnectorCreate | ConnectorUpdate) => Promise<void>
  isSubmitting: boolean
}

export function ConnectorFormDialog({
  open,
  onOpenChange,
  connector,
  onSubmit,
  isSubmitting,
}: ConnectorFormDialogProps) {
  const [name, setName] = useState("")
  const [description, setDescription] = useState("")
  const [baseUrl, setBaseUrl] = useState("")
  const [authType, setAuthType] = useState("none")
  // Auth config fields
  const [tokenPrefix, setTokenPrefix] = useState("Bearer")
  const [headerName, setHeaderName] = useState("X-API-Key")
  // Default credentials (for testing / v0.6.1)
  const [defaultToken, setDefaultToken] = useState("")
  const [defaultApiKey, setDefaultApiKey] = useState("")
  const [defaultUsername, setDefaultUsername] = useState("")
  const [defaultPassword, setDefaultPassword] = useState("")

  // Pre-fill when editing or reset when creating
  useEffect(() => {
    if (!open) return
    if (connector) {
      setName(connector.name)
      setDescription(connector.description || "")
      setBaseUrl(connector.base_url)
      setAuthType(connector.auth_type)
      const cfg = connector.auth_config || {}
      setTokenPrefix(typeof cfg.token_prefix === "string" ? cfg.token_prefix : "Bearer")
      setHeaderName(typeof cfg.header_name === "string" ? cfg.header_name : "X-API-Key")
      setDefaultToken(typeof cfg.default_token === "string" ? cfg.default_token : "")
      setDefaultApiKey(typeof cfg.default_api_key === "string" ? cfg.default_api_key : "")
      setDefaultUsername(typeof cfg.default_username === "string" ? cfg.default_username : "")
      setDefaultPassword(typeof cfg.default_password === "string" ? cfg.default_password : "")
    } else {
      setName("")
      setDescription("")
      setBaseUrl("")
      setAuthType("none")
      setTokenPrefix("Bearer")
      setHeaderName("X-API-Key")
      setDefaultToken("")
      setDefaultApiKey("")
      setDefaultUsername("")
      setDefaultPassword("")
    }
  }, [open, connector])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    const trimmedName = name.trim()
    const trimmedUrl = baseUrl.trim()
    if (!trimmedName || !trimmedUrl) return

    let authConfig: Record<string, unknown> | null = null
    if (authType === "bearer") {
      authConfig = {
        token_prefix: tokenPrefix.trim() || "Bearer",
        ...(defaultToken.trim() && { default_token: defaultToken.trim() }),
      }
    } else if (authType === "api_key") {
      authConfig = {
        header_name: headerName.trim() || "X-API-Key",
        ...(defaultApiKey.trim() && { default_api_key: defaultApiKey.trim() }),
      }
    } else if (authType === "basic") {
      authConfig = {
        ...(defaultUsername.trim() && { default_username: defaultUsername.trim() }),
        ...(defaultPassword.trim() && { default_password: defaultPassword.trim() }),
      }
      // Only set if has content
      if (Object.keys(authConfig).length === 0) authConfig = null
    }

    const data: ConnectorCreate = {
      name: trimmedName,
      description: description.trim() || null,
      type: "api",
      base_url: trimmedUrl,
      auth_type: authType,
      ...(authConfig && { auth_config: authConfig }),
    }

    await onSubmit(data)
  }

  const isEditing = connector !== null

  const inputClass =
    "flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-xs transition-colors placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>
            {isEditing ? "Edit Connector" : "Create Connector"}
          </DialogTitle>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Name */}
          <div className="space-y-1.5">
            <label htmlFor="connector-name" className="text-sm font-medium">
              Name <span className="text-destructive">*</span>
            </label>
            <input
              id="connector-name"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="GitHub API"
              required
              className={inputClass}
            />
          </div>

          {/* Description */}
          <div className="space-y-1.5">
            <label htmlFor="connector-description" className="text-sm font-medium">
              Description
            </label>
            <textarea
              id="connector-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="A brief description of this connector..."
              rows={2}
              className="flex w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-xs transition-colors placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring resize-none"
            />
          </div>

          {/* Base URL */}
          <div className="space-y-1.5">
            <label htmlFor="connector-base-url" className="text-sm font-medium">
              Base URL <span className="text-destructive">*</span>
            </label>
            <input
              id="connector-base-url"
              type="text"
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              placeholder="https://api.example.com"
              required
              className={inputClass}
            />
          </div>

          {/* Auth Type */}
          <div className="space-y-1.5">
            <label htmlFor="connector-auth-type" className="text-sm font-medium">
              Auth Type
            </label>
            <select
              id="connector-auth-type"
              value={authType}
              onChange={(e) => setAuthType(e.target.value)}
              className={inputClass}
            >
              <option value="none">None</option>
              <option value="bearer">Bearer Token</option>
              <option value="api_key">API Key (Custom Header)</option>
              <option value="basic">Basic Auth (Username/Password)</option>
            </select>
          </div>

          {/* Bearer Token config */}
          {authType === "bearer" && (
            <div className="space-y-3 rounded-md border border-border p-3">
              <div className="space-y-1.5">
                <label htmlFor="connector-token-prefix" className="text-sm font-medium">
                  Token Prefix
                </label>
                <input
                  id="connector-token-prefix"
                  type="text"
                  value={tokenPrefix}
                  onChange={(e) => setTokenPrefix(e.target.value)}
                  placeholder="Bearer"
                  className={inputClass}
                />
                <p className="text-xs text-muted-foreground">
                  Prefix before the token in Authorization header. Default: Bearer.
                </p>
              </div>
              <div className="space-y-1.5">
                <label htmlFor="connector-default-token" className="text-sm font-medium">
                  Default Token
                </label>
                <input
                  id="connector-default-token"
                  type="password"
                  value={defaultToken}
                  onChange={(e) => setDefaultToken(e.target.value)}
                  placeholder="ghp_xxxxxxxxxxxx"
                  className={inputClass}
                />
                <p className="text-xs text-muted-foreground">
                  Used for testing. Per-user credentials will override this in a future version.
                </p>
              </div>
            </div>
          )}

          {/* API Key config */}
          {authType === "api_key" && (
            <div className="space-y-3 rounded-md border border-border p-3">
              <div className="space-y-1.5">
                <label htmlFor="connector-header-name" className="text-sm font-medium">
                  Header Name
                </label>
                <input
                  id="connector-header-name"
                  type="text"
                  value={headerName}
                  onChange={(e) => setHeaderName(e.target.value)}
                  placeholder="X-API-Key"
                  className={inputClass}
                />
                <p className="text-xs text-muted-foreground">
                  The HTTP header used to send the API key. Default: X-API-Key.
                </p>
              </div>
              <div className="space-y-1.5">
                <label htmlFor="connector-default-api-key" className="text-sm font-medium">
                  Default API Key
                </label>
                <input
                  id="connector-default-api-key"
                  type="password"
                  value={defaultApiKey}
                  onChange={(e) => setDefaultApiKey(e.target.value)}
                  placeholder="sk-xxxxxxxxxxxx"
                  className={inputClass}
                />
                <p className="text-xs text-muted-foreground">
                  Used for testing. Per-user credentials will override this in a future version.
                </p>
              </div>
            </div>
          )}

          {/* Basic Auth config */}
          {authType === "basic" && (
            <div className="space-y-3 rounded-md border border-border p-3">
              <div className="space-y-1.5">
                <label htmlFor="connector-default-username" className="text-sm font-medium">
                  Username
                </label>
                <input
                  id="connector-default-username"
                  type="text"
                  value={defaultUsername}
                  onChange={(e) => setDefaultUsername(e.target.value)}
                  placeholder="admin"
                  className={inputClass}
                />
              </div>
              <div className="space-y-1.5">
                <label htmlFor="connector-default-password" className="text-sm font-medium">
                  Password
                </label>
                <input
                  id="connector-default-password"
                  type="password"
                  value={defaultPassword}
                  onChange={(e) => setDefaultPassword(e.target.value)}
                  placeholder="********"
                  className={inputClass}
                />
              </div>
              <p className="text-xs text-muted-foreground">
                Used for testing. Per-user credentials will override this in a future version.
              </p>
            </div>
          )}

          <DialogFooter>
            <Button
              type="button"
              variant="ghost"
              onClick={() => onOpenChange(false)}
              disabled={isSubmitting}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={isSubmitting || !name.trim() || !baseUrl.trim()}>
              {isSubmitting && <Loader2 className="h-4 w-4 animate-spin" />}
              {isEditing ? "Save Changes" : "Create"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
