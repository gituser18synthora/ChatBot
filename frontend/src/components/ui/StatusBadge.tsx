import { Badge } from "./primitives";
import { Spinner } from "./primitives";
import { Icon } from "./Icons";
import type { DocumentStatus, KnowledgeBaseStatus } from "@/api/types";
import { roleLabel, titleCase } from "@/lib/utils";

export function DocStatusBadge({ status }: { status: DocumentStatus }) {
  switch (status) {
    case "completed":
      return (
        <Badge tone="green">
          <Icon.Check width={12} height={12} /> Indexed
        </Badge>
      );
    case "processing":
      return (
        <span title="Being ingested by the retrieval engine — this updates to Indexed automatically.">
          <Badge tone="blue">
            <Spinner className="h-3 w-3" /> Processing
          </Badge>
        </span>
      );
    case "uploading":
      return (
        <Badge tone="blue">
          <Spinner className="h-3 w-3" /> Uploading
        </Badge>
      );
    case "pending":
      return <Badge tone="amber">Pending</Badge>;
    case "failed":
      return <Badge tone="red">Failed</Badge>;
    case "deleted":
      return <Badge tone="gray">Deleted</Badge>;
    default:
      return <Badge tone="gray">{titleCase(status)}</Badge>;
  }
}

export function ActiveBadge({ status }: { status: "active" | "inactive" }) {
  return status === "active" ? <Badge tone="green">Active</Badge> : <Badge tone="gray">Inactive</Badge>;
}

export function KBStatusBadge({ status }: { status: KnowledgeBaseStatus }) {
  switch (status) {
    case "ready":
      return (
        <Badge tone="green">
          <Icon.Check width={12} height={12} /> Ready
        </Badge>
      );
    case "processing":
      return (
        <Badge tone="blue">
          <Spinner className="h-3 w-3" /> Processing
        </Badge>
      );
    case "pending":
      return <Badge tone="amber">Pending</Badge>;
    case "failed":
      return <Badge tone="red">Failed</Badge>;
    case "inactive":
      return <Badge tone="gray">Inactive</Badge>;
    default:
      return <Badge tone="gray">{titleCase(status)}</Badge>;
  }
}

export function RoleBadge({ role }: { role: string }) {
  const tone = role === "super_admin" ? "purple" : role === "tenant_admin" ? "blue" : "gray";
  return <Badge tone={tone as never}>{roleLabel(role)}</Badge>;
}
