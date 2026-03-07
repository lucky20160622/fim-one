"use client"

import {
  type LucideIcon,
  Cat,
  Dog,
  Bird,
  Fish,
  Rabbit,
  Squirrel,
  Bug,
  Leaf,
  Flower2,
  Star,
  Heart,
  Moon,
  Sun,
  Cloud,
  Rocket,
  Gamepad2,
} from "lucide-react"
import { cn } from "@/lib/utils"
import { Avatar, AvatarImage, AvatarFallback } from "@/components/ui/avatar"

/* ── Icon definitions (shape only, no color) ── */

export interface AvatarIconConfig {
  id: string
  icon: LucideIcon
}

export const AVATAR_ICONS: AvatarIconConfig[] = [
  { id: "cat", icon: Cat },
  { id: "dog", icon: Dog },
  { id: "bird", icon: Bird },
  { id: "fish", icon: Fish },
  { id: "rabbit", icon: Rabbit },
  { id: "squirrel", icon: Squirrel },
  { id: "bug", icon: Bug },
  { id: "leaf", icon: Leaf },
  { id: "flower", icon: Flower2 },
  { id: "star", icon: Star },
  { id: "heart", icon: Heart },
  { id: "moon", icon: Moon },
  { id: "sun", icon: Sun },
  { id: "cloud", icon: Cloud },
  { id: "rocket", icon: Rocket },
  { id: "gamepad", icon: Gamepad2 },
]

/* ── Color palette ── */

export interface AvatarColorConfig {
  id: string
  bg: string
}

export const AVATAR_COLORS: AvatarColorConfig[] = [
  { id: "gray", bg: "bg-gradient-to-br from-gray-400 to-gray-600" },
  { id: "slate", bg: "bg-gradient-to-br from-slate-500 to-slate-700" },
  { id: "red", bg: "bg-gradient-to-br from-red-500 to-rose-700" },
  { id: "orange", bg: "bg-gradient-to-br from-orange-500 to-amber-700" },
  { id: "amber", bg: "bg-gradient-to-br from-amber-500 to-yellow-700" },
  { id: "green", bg: "bg-gradient-to-br from-green-500 to-emerald-700" },
  { id: "teal", bg: "bg-gradient-to-br from-cyan-500 to-teal-700" },
  { id: "blue", bg: "bg-gradient-to-br from-blue-500 to-indigo-700" },
  { id: "purple", bg: "bg-gradient-to-br from-violet-500 to-purple-700" },
  { id: "pink", bg: "bg-gradient-to-br from-pink-500 to-fuchsia-700" },
]

/* ── Legacy color mapping for old "builtin:{icon}" format ── */

const LEGACY_ICON_COLORS: Record<string, string> = {
  cat: "orange", dog: "blue", bird: "green", fish: "teal",
  rabbit: "pink", squirrel: "amber", bug: "red", leaf: "green",
  flower: "purple", star: "orange", heart: "pink", moon: "blue",
  sun: "amber", cloud: "blue", rocket: "purple", gamepad: "teal",
}

/* ── Parse "builtin:icon" or "builtin:icon:color" ── */

export function parseBuiltinAvatar(avatar: string): { iconId: string; colorId: string } | null {
  if (!avatar.startsWith("builtin:")) return null
  const rest = avatar.slice(8)
  const sep = rest.indexOf(":")
  if (sep === -1) {
    // Legacy format: "builtin:cat"
    return { iconId: rest, colorId: LEGACY_ICON_COLORS[rest] || "blue" }
  }
  return { iconId: rest.slice(0, sep), colorId: rest.slice(sep + 1) }
}

/* ── Component ── */

interface UserAvatarProps {
  avatar: string | null | undefined
  fallback: string
  userId?: string
  className?: string
  iconClassName?: string
}

export function UserAvatar({
  avatar,
  fallback,
  userId,
  className = "h-8 w-8",
  iconClassName = "h-4 w-4",
}: UserAvatarProps) {
  if (avatar?.startsWith("builtin:")) {
    const parsed = parseBuiltinAvatar(avatar)
    if (parsed) {
      const iconCfg = AVATAR_ICONS.find((i) => i.id === parsed.iconId)
      const colorCfg = AVATAR_COLORS.find((c) => c.id === parsed.colorId)
      if (iconCfg && colorCfg) {
        const Icon = iconCfg.icon
        return (
          <div
            className={cn(
              "rounded-full flex items-center justify-center shrink-0",
              colorCfg.bg,
              className,
            )}
          >
            <Icon className={cn("text-white", iconClassName)} />
          </div>
        )
      }
    }
  }

  return (
    <Avatar className={cn("shrink-0", className)}>
      {avatar && userId && (
        <AvatarImage src={`/api/auth/avatar/${userId}?v=${encodeURIComponent(avatar)}`} alt="Avatar" />
      )}
      <AvatarFallback className="bg-primary/10 text-xs text-primary">
        {fallback}
      </AvatarFallback>
    </Avatar>
  )
}
