"use client"

import { useState, useEffect, useCallback } from "react"
import { useParams, useRouter } from "next/navigation"
import { ArrowLeft, Loader2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { useAuth } from "@/contexts/auth-context"
import { connectorApi } from "@/lib/api"
import { ConnectorSettingsForm } from "@/components/connectors/connector-settings-form"
import { ActionManager } from "@/components/connectors/action-manager"
import { AIActionPanel } from "@/components/connectors/ai-action-panel"
import type { ConnectorResponse } from "@/types/connector"

export default function ConnectorEditorPage() {
  const params = useParams()
  const router = useRouter()
  const { user, isLoading: authLoading } = useAuth()

  const id = params.id as string
  const [connector, setConnector] = useState<ConnectorResponse | null>(null)
  const [isNew, setIsNew] = useState(id === "new")
  const [activeTab, setActiveTab] = useState<string>("connector")
  const [isLoading, setIsLoading] = useState(id !== "new")
  const [formDirty, setFormDirty] = useState(false)

  // Auth guard
  useEffect(() => {
    if (!authLoading && !user) {
      router.replace("/login")
    }
  }, [authLoading, user, router])

  const loadConnector = useCallback(async () => {
    if (id === "new") return
    try {
      setIsLoading(true)
      const data = await connectorApi.get(id)
      setConnector(data)
      setIsNew(false)
    } catch (err) {
      console.error("Failed to load connector:", err)
      router.replace("/connectors")
    } finally {
      setIsLoading(false)
    }
  }, [id, router])

  useEffect(() => {
    if (user && id !== "new") loadConnector()
  }, [user, id, loadConnector])

  const handleConnectorSaved = (saved: ConnectorResponse) => {
    setConnector(saved)
    if (isNew) {
      setIsNew(false)
      router.replace(`/connectors/${saved.id}`)
    }
  }

  const reload = async () => {
    if (!connector) return
    try {
      const data = await connectorApi.get(connector.id)
      setConnector(data)
    } catch (err) {
      console.error("Failed to reload connector:", err)
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

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Top bar */}
      <div className="flex items-center gap-3 px-4 py-3 border-b border-border/40 shrink-0">
        <Button
          variant="ghost"
          size="icon-xs"
          onClick={() => router.push("/connectors")}
          title="Back to Connectors"
        >
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <h1 className="text-sm font-semibold text-foreground truncate">
          {isNew ? "New Connector" : connector?.name || "Connector"}
        </h1>
      </div>

      {/* Main content: left AI chat + right tabs */}
      <div className="flex flex-1 min-h-0">
        {/* Left: AI Chat Panel (1/3) */}
        <div className="w-1/3 border-r border-border flex flex-col min-h-0">
          <AIActionPanel
            connectorId={connector?.id ?? null}
            onActionsChanged={reload}
            onConnectorUpdated={(updated) => setConnector(updated)}
            formDirty={formDirty}
          />
        </div>

        {/* Right: Tabs (2/3) */}
        <div className="w-2/3 flex flex-col min-h-0">
          <Tabs
            value={activeTab}
            onValueChange={setActiveTab}
            className="flex flex-col h-full"
          >
            <TabsList className="shrink-0 mx-4 mt-3 w-fit">
              <TabsTrigger value="connector">Connector</TabsTrigger>
              <TabsTrigger value="actions" disabled={isNew}>
                Actions
                {connector && connector.actions.length > 0 && (
                  <span className="ml-1.5 text-xs text-muted-foreground">
                    ({connector.actions.length})
                  </span>
                )}
              </TabsTrigger>
            </TabsList>

            <TabsContent value="connector" className="flex-1 min-h-0 px-4 py-4">
              <ConnectorSettingsForm
                connector={connector}
                onSaved={handleConnectorSaved}
                onDirtyChange={setFormDirty}
              />
            </TabsContent>

            <TabsContent value="actions" className="flex-1 min-h-0">
              {connector && (
                <ActionManager connector={connector} onChanged={reload} />
              )}
            </TabsContent>
          </Tabs>
        </div>
      </div>
    </div>
  )
}
