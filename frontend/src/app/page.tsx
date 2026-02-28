"use client"

import { useSearchParams } from "next/navigation"
import { useEffect, useRef } from "react"
import { useRouter } from "next/navigation"
import { PlaygroundPage } from "@/components/playground/playground-page"

export default function RootPage() {
  const searchParams = useSearchParams()
  const router = useRouter()
  const cParam = searchParams.get("c")
  const redirectedRef = useRef(false)

  // Redirect to /new when there is no ?c= param
  useEffect(() => {
    if (!cParam && !redirectedRef.current) {
      redirectedRef.current = true
      router.replace("/new")
    }
  }, [cParam, router])

  // If no ?c= param, show nothing while redirecting
  if (!cParam) return null

  // With ?c=<id>, render the playground to load that conversation
  return <PlaygroundPage />
}
