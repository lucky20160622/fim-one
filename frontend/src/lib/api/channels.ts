/**
 * Channels API client.
 *
 * Wraps `/api/channels` CRUD + test-send. The backend contract is fixed in
 * `feat/roadshow-feishu-channel`; the frontend mirrors the same schema
 * (see `@/types/channel`).
 */
import { apiFetch } from "@/lib/api"
import type {
  Channel,
  ChannelCreateRequest,
  ChannelListResponse,
  ChannelTestResponse,
  ChannelUpdateRequest,
  ChatDiscoveryRequest,
  ChatDiscoveryResponse,
  ConfirmationStatus,
  TestApprovalRequest,
  TestApprovalResponse,
} from "@/types/channel"

export const channelsApi = {
  list: (orgId: string) => {
    const qs = new URLSearchParams({ org_id: orgId })
    return apiFetch<ChannelListResponse>(`/api/channels?${qs.toString()}`)
  },

  get: (id: string) => apiFetch<Channel>(`/api/channels/${id}`),

  create: (body: ChannelCreateRequest) =>
    apiFetch<Channel>("/api/channels", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  update: (id: string, body: ChannelUpdateRequest) =>
    apiFetch<Channel>(`/api/channels/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  delete: (id: string) =>
    apiFetch<void>(`/api/channels/${id}`, { method: "DELETE" }),

  test: (id: string) =>
    apiFetch<ChannelTestResponse>(`/api/channels/${id}/test`, {
      method: "POST",
    }),

  /**
   * Hook Playground — kick off a real approval round-trip.
   *
   * The backend creates a genuine `ConfirmationRequest` row and sends a
   * production-grade card to the chat.  Operators can press Approve/Reject
   * in Feishu; the card callback flips the row's status; the UI then
   * reflects the decision via `getConfirmation()`.
   */
  testApproval: (id: string, body: TestApprovalRequest = {}) =>
    apiFetch<TestApprovalResponse>(`/api/channels/${id}/test-approval`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  /** Fetch the current state of a pending approval (polled by the UI). */
  getConfirmation: (channelId: string, confirmationId: string) =>
    apiFetch<ConfirmationStatus>(
      `/api/channels/${channelId}/confirmations/${confirmationId}`,
    ),

  /**
   * Ask the backend to list Feishu groups the given app/bot is a member of.
   * Used by the chat picker UI in the channel form dialog.
   */
  discoverChats: (body: ChatDiscoveryRequest) =>
    apiFetch<ChatDiscoveryResponse>("/api/channels/discover-chats", {
      method: "POST",
      body: JSON.stringify(body),
    }),
}
