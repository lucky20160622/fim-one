export interface EvalDatasetResponse {
  id: string
  name: string
  description: string | null
  case_count: number
  created_at: string
  updated_at: string | null
}

export interface EvalDatasetCreate {
  name: string
  description?: string | null
}

export interface EvalDatasetUpdate {
  name?: string
  description?: string | null
}

export interface EvalCaseResponse {
  id: string
  dataset_id: string
  prompt: string
  expected_behavior: string
  assertions: string[] | null
  created_at: string
  updated_at: string | null
}

export interface EvalCaseCreate {
  prompt: string
  expected_behavior: string
  assertions?: string[] | null
}

export interface EvalCaseUpdate {
  prompt?: string
  expected_behavior?: string
  assertions?: string[] | null
}

export interface EvalRunResponse {
  id: string
  agent_id: string
  agent_name: string | null
  dataset_id: string
  dataset_name: string | null
  status: "pending" | "running" | "completed" | "failed"
  total_cases: number
  passed_cases: number
  failed_cases: number
  avg_latency_ms: number | null
  total_tokens: number | null
  error_message: string | null
  completed_at: string | null
  created_at: string
  updated_at: string | null
}

export interface EvalRunCreate {
  agent_id: string
  dataset_id: string
}

export interface EvalCaseResultResponse {
  id: string
  run_id: string
  case_id: string
  case_prompt: string | null
  case_expected_behavior: string | null
  status: "pass" | "fail" | "error"
  agent_answer: string | null
  grader_reasoning: string | null
  latency_ms: number | null
  prompt_tokens: number | null
  completion_tokens: number | null
  created_at: string
}

export interface EvalRunDetailResponse extends EvalRunResponse {
  results: EvalCaseResultResponse[]
}
