"use client"

import { useState, useEffect } from "react"
import { Loader2, KeyRound, Trash2 } from "lucide-react"
import { toast } from "sonner"
import { useTranslations } from "next-intl"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { connectorApi } from "@/lib/api"
import type { ConnectorResponse, MyCredentialStatus } from "@/types/connector"

interface MyCredentialsFormProps {
  connector: ConnectorResponse
}

export function MyCredentialsForm({ connector }: MyCredentialsFormProps) {
  const t = useTranslations("connectors")
  const tc = useTranslations("common")

  const [status, setStatus] = useState<MyCredentialStatus | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [isSaving, setIsSaving] = useState(false)
  const [isDeleting, setIsDeleting] = useState(false)

  // Credential fields
  const [token, setToken] = useState("")
  const [apiKey, setApiKey] = useState("")
  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")

  useEffect(() => {
    connectorApi.getMyCredentials(connector.id)
      .then(setStatus)
      .catch(() => setStatus(null))
      .finally(() => setIsLoading(false))
  }, [connector.id])

  const handleSave = async () => {
    setIsSaving(true)
    try {
      await connectorApi.upsertMyCredentials(connector.id, {
        token: connector.auth_type === "bearer" ? token || undefined : undefined,
        api_key: connector.auth_type === "api_key" ? apiKey || undefined : undefined,
        username: connector.auth_type === "basic" ? username || undefined : undefined,
        password: connector.auth_type === "basic" ? password || undefined : undefined,
      })
      toast.success(t("myCredentialsSaved"))
      setStatus(prev => prev ? { ...prev, has_credentials: true } : null)
      // Clear fields after save
      setToken("")
      setApiKey("")
      setUsername("")
      setPassword("")
    } catch {
      toast.error(t("myCredentialsSaveFailed"))
    } finally {
      setIsSaving(false)
    }
  }

  const handleDelete = async () => {
    setIsDeleting(true)
    try {
      await connectorApi.deleteMyCredentials(connector.id)
      toast.success(t("myCredentialsDeleted"))
      setStatus(prev => prev ? { ...prev, has_credentials: false } : null)
    } catch {
      toast.error(tc("error"))
    } finally {
      setIsDeleting(false)
    }
  }

  if (isLoading) return null

  const helpText = status?.allow_fallback
    ? t("myCredentialsHelpWithFallback")
    : t("myCredentialsHelpRequired")

  return (
    <Card className="mt-6">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <KeyRound className="h-4 w-4" />
          {t("myCredentials")}
        </CardTitle>
        <CardDescription>{helpText}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {status?.has_credentials && (
          <p className="text-sm text-muted-foreground">{t("myCredentialsSet")}</p>
        )}

        {connector.auth_type === "bearer" && (
          <div className="space-y-1.5">
            <Label htmlFor="my-token">Token</Label>
            <Input
              id="my-token"
              type="password"
              value={token}
              onChange={e => setToken(e.target.value)}
              placeholder={status?.has_credentials ? "••••••••" : ""}
            />
          </div>
        )}

        {connector.auth_type === "api_key" && (
          <div className="space-y-1.5">
            <Label htmlFor="my-api-key">API Key</Label>
            <Input
              id="my-api-key"
              type="password"
              value={apiKey}
              onChange={e => setApiKey(e.target.value)}
              placeholder={status?.has_credentials ? "••••••••" : ""}
            />
          </div>
        )}

        {connector.auth_type === "basic" && (
          <>
            <div className="space-y-1.5">
              <Label htmlFor="my-username">Username</Label>
              <Input
                id="my-username"
                value={username}
                onChange={e => setUsername(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="my-password">Password</Label>
              <Input
                id="my-password"
                type="password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                placeholder={status?.has_credentials ? "••••••••" : ""}
              />
            </div>
          </>
        )}

        <div className="flex gap-2">
          <Button onClick={handleSave} disabled={isSaving} size="sm">
            {isSaving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {tc("save")}
          </Button>
          {status?.has_credentials && (
            <Button
              variant="outline"
              size="sm"
              onClick={handleDelete}
              disabled={isDeleting}
            >
              {isDeleting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              <Trash2 className="mr-2 h-4 w-4" />
              {tc("delete")}
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  )
}
