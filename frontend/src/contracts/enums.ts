export const ACTION_TYPES = [
  "READ_FILE",
  "SEARCH_CODE",
  "APPLY_PATCH",
  "CREATE_FILE",
  "DELETE_FILE",
  "RUN_COMMAND",
] as const;

export const TRUST_LEVELS = [
  "SYSTEM",
  "USER_INPUT",
  "REPOSITORY_CONTENT",
  "LLM_OUTPUT",
  "TOOL_OUTPUT",
] as const;

export type ActionType = (typeof ACTION_TYPES)[number];
export type TrustLevel = (typeof TRUST_LEVELS)[number];
