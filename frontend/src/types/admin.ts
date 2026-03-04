export interface AdminUser {
  id: string
  username: string
  display_name: string | null
  email: string | null
  is_admin: boolean
  is_active: boolean
  created_at: string
}
