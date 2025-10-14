"""Pydantic models for status response validation."""

from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class RepoInfo(BaseModel):
    """Repository information"""
    name: str
    full_name: str
    url: str
    updated_at: str
    exists: bool = True


class IssueInfo(BaseModel):
    """Issue information"""
    number: int
    title: str
    labels: List[str] = Field(default_factory=list)
    state: str


class IssuesData(BaseModel):
    """Issues data for a service"""
    count: int
    items: List[IssueInfo] = Field(default_factory=list)


class PullRequestInfo(BaseModel):
    """Pull request information"""
    model_config = ConfigDict(populate_by_name=True)

    number: int
    title: str
    state: str
    branch: str = Field(alias="headRefName", default="")
    is_draft: bool = Field(alias="isDraft", default=False)
    is_release: bool = False


class PullRequestsData(BaseModel):
    """Pull requests data for a service"""
    count: int
    items: List[PullRequestInfo] = Field(default_factory=list)


class WorkflowRun(BaseModel):
    """Workflow run information"""
    model_config = ConfigDict(populate_by_name=True)

    name: str
    status: str
    conclusion: Optional[str] = None
    created_at: str = Field(alias="createdAt", default="")
    updated_at: str = Field(alias="updatedAt", default="")


class WorkflowsData(BaseModel):
    """Workflows data for a service"""
    recent: List[WorkflowRun] = Field(default_factory=list)


class ServiceData(BaseModel):
    """Complete data for a service"""
    repo: RepoInfo
    issues: IssuesData = Field(default_factory=IssuesData)
    pull_requests: PullRequestsData = Field(default_factory=PullRequestsData)
    workflows: WorkflowsData = Field(default_factory=WorkflowsData)


class StatusResponse(BaseModel):
    """Complete status response from copilot"""
    timestamp: str
    services: Dict[str, ServiceData]


__all__ = [
    "RepoInfo",
    "IssueInfo",
    "IssuesData",
    "PullRequestInfo",
    "PullRequestsData",
    "WorkflowRun",
    "WorkflowsData",
    "ServiceData",
    "StatusResponse",
]
