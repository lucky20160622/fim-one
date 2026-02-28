import type { Node } from "@xyflow/react"
import type { StepState } from "@/hooks/use-dag-steps"

export interface StepNodeData {
  step_id: string
  task: string
  status: "pending" | "running" | "completed" | "failed"
  tool_hint?: string
  duration?: number
  started_at?: number
  tools_used?: string[]
  state: StepState
  [key: string]: unknown // ReactFlow requires index signature
}

export type StepFlowNode = Node<StepNodeData, "step">
