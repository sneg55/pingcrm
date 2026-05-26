import type { components } from "./api-types";
import type { ContactCreateInput } from "@/hooks/use-contacts";

type Schemas = components["schemas"];

export function toContactCreateBody(
  input: ContactCreateInput
): Schemas["ContactCreate"] {
  const { organization_id: _organizationId, ...rest } = input;
  return {
    ...rest,
    emails: input.emails ?? [],
    phones: input.phones ?? [],
    tags: input.tags ?? [],
    priority_level: input.priority_level ?? "medium",
  };
}
