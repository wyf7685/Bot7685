from typing import Set
from pydantic import BaseModel, Field


class Config(BaseModel):
    exe_code_user: Set[str] = Field(default_factory=set)
    exe_code_group: Set[str] = Field(default_factory=set)
