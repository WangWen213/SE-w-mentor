from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from se_mentor.contracts.enums import ActionType


class _ActionBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str


class ReadFileAction(_ActionBase):
    action_type: Literal[ActionType.READ_FILE]
    path: str


class SearchCodeAction(_ActionBase):
    action_type: Literal[ActionType.SEARCH_CODE]
    query: str


class ApplyPatchAction(_ActionBase):
    action_type: Literal[ActionType.APPLY_PATCH]
    patch: str


class CreateFileAction(_ActionBase):
    action_type: Literal[ActionType.CREATE_FILE]
    path: str
    content: str


class DeleteFileAction(_ActionBase):
    action_type: Literal[ActionType.DELETE_FILE]
    path: str


class RunCommandAction(_ActionBase):
    action_type: Literal[ActionType.RUN_COMMAND]
    program: str
    args: list[str] = Field(default_factory=list)


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
