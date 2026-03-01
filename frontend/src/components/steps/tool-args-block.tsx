"use client"

import { MarkdownContent } from "@/lib/markdown"
import { CollapsibleBlock } from "./collapsible-block"
import { SectionToggle } from "./section-toggle"

interface ToolArgsBlockProps {
  args: Record<string, unknown>
  size?: "default" | "compact"
  defaultCollapsed?: boolean
  className?: string
}

const DEFAULT_MD_CLS = "text-xs [&_pre]:my-0 [&_pre]:p-0 [&_pre]:bg-transparent [&_pre]:rounded-none"
const COMPACT_MD_CLS = "text-[11px] [&_pre]:my-0 [&_pre]:p-2"

export function ToolArgsBlock({
  args,
  size = "default",
  defaultCollapsed = false,
  className,
}: ToolArgsBlockProps) {
  const isCompact = size === "compact"
  const mdCls = isCompact ? COMPACT_MD_CLS : DEFAULT_MD_CLS

  const content = typeof args.code === "string"
    ? <CodeArgsContent args={args} mdCls={mdCls} isCompact={isCompact} />
    : <JsonArgsContent args={args} mdCls={mdCls} />

  // When defaultCollapsed, use SectionToggle (fully hidden until click)
  if (defaultCollapsed) {
    return (
      <div className={className ?? ""}>
        <SectionToggle label="Arguments">
          {content}
        </SectionToggle>
      </div>
    )
  }

  // Otherwise show inline with CollapsibleBlock (overflow truncation)
  const containerCls = isCompact
    ? "rounded bg-muted/30 border border-border/30 p-2"
    : "rounded-md border border-border/50 bg-muted/30 p-3"
  const labelCls = isCompact
    ? "text-[10px] font-medium text-muted-foreground mb-0.5 uppercase tracking-wider"
    : "text-xs font-medium text-muted-foreground mb-1 uppercase tracking-wider"

  return (
    <div className={`${containerCls} ${className ?? ""}`}>
      <p className={labelCls}>Arguments</p>
      {content}
    </div>
  )
}

function CodeArgsContent({ args, mdCls, isCompact }: { args: Record<string, unknown>; mdCls: string; isCompact: boolean }) {
  const rest = { ...args }
  delete rest.code
  const hasRest = Object.keys(rest).length > 0
  return (
    <>
      <CollapsibleBlock>
        <MarkdownContent
          content={`\`\`\`python\n${args.code}\n\`\`\``}
          className={mdCls}
        />
      </CollapsibleBlock>
      {hasRest && (
        <div className={isCompact ? "mt-1" : "mt-2"}>
          <CollapsibleBlock>
            <MarkdownContent
              content={`\`\`\`json\n${JSON.stringify(rest, null, 2)}\n\`\`\``}
              className={mdCls}
            />
          </CollapsibleBlock>
        </div>
      )}
    </>
  )
}

function JsonArgsContent({ args, mdCls }: { args: Record<string, unknown>; mdCls: string }) {
  return (
    <CollapsibleBlock>
      <MarkdownContent
        content={`\`\`\`json\n${JSON.stringify(args, null, 2)}\n\`\`\``}
        className={mdCls}
      />
    </CollapsibleBlock>
  )
}
