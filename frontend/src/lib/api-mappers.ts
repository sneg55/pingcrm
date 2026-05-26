import type { components } from "./api-types";
import type { ContactCreateInput } from "@/hooks/use-contacts";
import type { UpdateSuggestionInput } from "@/hooks/use-suggestions";

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

export function toContactUpdateBody(
  input: Partial<ContactCreateInput>
): Schemas["ContactUpdate"] {
  return { ...input };
}

export type SuggestionUpdateInput = UpdateSuggestionInput & {
  status: NonNullable<UpdateSuggestionInput["status"]>;
};

export function toSuggestionUpdateBody(
  input: SuggestionUpdateInput
): Schemas["SuggestionUpdateBody"] {
  return { ...input };
}
