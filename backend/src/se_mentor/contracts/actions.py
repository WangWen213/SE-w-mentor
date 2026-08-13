from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from se_mentor.contracts.enums import ActionType


class _ActionBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_type: ActionType
    parameters: BaseModel
    reason: str


class ReadFileParameters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    start_line: int
    end_line: int


class ReadFileAction(_ActionBase):
    action_type: Literal[ActionType.READ_FILE]
    parameters: ReadFileParameters


class SearchCodeParameters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str


class SearchCodeAction(_ActionBase):
    action_type: Literal[ActionType.SEARCH_CODE]
    parameters: SearchCodeParameters


class PatchReplacement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    old: str
    new: str


class StructuredPatchPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    relative_path: str
    expected_sha256: str | None = None
    replacements: list[PatchReplacement]
    target_evidence: dict[str, object] | None = None


class ApplyPatchAction(_ActionBase):
    action_type: Literal[ActionType.APPLY_PATCH]
    parameters: StructuredPatchPayload


class CreateFileParameters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    content: str


class CreateFileAction(_ActionBase):
    action_type: Literal[ActionType.CREATE_FILE]
    parameters: CreateFileParameters


class DeleteFileParameters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str


class DeleteFileAction(_ActionBase):
    action_type: Literal[ActionType.DELETE_FILE]
    parameters: DeleteFileParameters


class RunCommandParameters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    program: str
    args: list[str]


class RunCommandAction(_ActionBase):
    action_type: Literal[ActionType.RUN_COMMAND]
    parameters: RunCommandParameters


AgentAction = Annotated[
    ReadFileAction
    | SearchCodeAction
    | ApplyPatchAction
    | CreateFileAction
    | DeleteFileAction
    | RunCommandAction,
    Field(discriminator="action_type"),
]

AgentActionAdapter: TypeAdapter[AgentAction] = TypeAdapter(AgentAction)
