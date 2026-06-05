from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

# --- Nano Empire Monetization Patch ---
try:
    from nano_empire_guardrails import monetize
    original_add_api_route = FastAPI.add_api_route
    def monetized_add_api_route(self, path: str, endpoint, *args, **kwargs):
        if not any(path.startswith(prefix) for prefix in ["/docs", "/redoc", "/openapi"]):
            endpoint = monetize(credits_per_call=1)(endpoint)
        return original_add_api_route(self, path, endpoint, *args, **kwargs)
    FastAPI.add_api_route = monetized_add_api_route
except ImportError:
    pass
# --------------------------------------

import logging
from pathlib import Path
from typing import List, Optional
from enum import Enum
import git
from pydantic import BaseModel, Field

app = FastAPI(
    title="Git Management API",
    version="0.1.0",
    description="An API to manage Git repositories with explicit endpoints, inputs, and outputs for better OpenAPI schemas.",
)

origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ----------------- ENUMS -----------------


class GitTools(str, Enum):
    STATUS = "status"
    DIFF_UNSTAGED = "diff_unstaged"
    DIFF_STAGED = "diff_staged"
    DIFF = "diff"
    COMMIT = "commit"
    ADD = "add"
    RESET = "reset"
    LOG = "log"
    CREATE_BRANCH = "create_branch"
    CHECKOUT = "checkout"
    SHOW = "show"
    INIT = "init"


# ----------------- MODELS -----------------


class GitRepoPath(BaseModel):
    repo_path: str = Field(..., description="File system path to the Git repository.")


class GitStatusRequest(GitRepoPath):
    pass


class GitDiffUnstagedRequest(GitRepoPath):
    pass


class GitDiffStagedRequest(GitRepoPath):
    pass


class GitDiffRequest(GitRepoPath):
    target: str = Field(..., description="The branch or commit to diff against.")


class GitCommitRequest(GitRepoPath):
    message: str = Field(..., description="Commit message for recording the change.")


class GitAddRequest(GitRepoPath):
    files: List[str] = Field(
        ..., description="List of file paths to add to the staging area."
    )


class GitResetRequest(GitRepoPath):
    pass


class GitLogRequest(GitRepoPath):
    max_count: int = Field(10, description="Maximum number of commits to retrieve.")


class GitCreateBranchRequest(GitRepoPath):
    branch_name: str = Field(..., description="Name of the branch to create.")
    base_branch: Optional[str] = Field(
        None, description="Optional base branch name to create the new branch from."
    )


class GitCheckoutRequest(GitRepoPath):
    branch_name: str = Field(..., description="Branch name to checkout.")


class GitShowRequest(GitRepoPath):
    revision: str = Field(
        ..., description="The commit hash or branch/tag name to show."
    )


class GitInitRequest(GitRepoPath):
    pass


class TextResponse(BaseModel):
    result: str = Field(..., description="Description of the operation result.")


class LogResponse(BaseModel):
    commits: List[str] = Field(
        ..., description="A list of formatted commit log entries."
    )


# ----------------- UTILITY FUNCTIONS -----------------


def get_repo(repo_path: str) -> git.Repo:
    try:
        return git.Repo(repo_path)
    except git.InvalidGitRepositoryError:
        raise HTTPException(
            status_code=400, detail=f"Invalid Git repository at '{repo_path}'"
        )


# ----------------- API ENDPOINTS -----------------


@app.post(
    "/status",
    response_model=TextResponse,
    description="Get the current status of the Git repository.",
)
def get_status(request: GitStatusRequest):
    repo = get_repo(request.repo_path)
    status = repo.git.status()
    return TextResponse(result=status)


@app.post(
    "/diff_unstaged",
    response_model=TextResponse,
    description="Get differences of unstaged changes.",
)
def diff_unstaged(request: GitDiffUnstagedRequest):
    repo = get_repo(request.repo_path)
    diff = repo.git.diff()
    return TextResponse(result=diff)


@app.post(
    "/diff_staged",
    response_model=TextResponse,
    description="Get differences of staged changes.",
)
def diff_staged(request: GitDiffStagedRequest):
    repo = get_repo(request.repo_path)
    diff = repo.git.diff("--cached")
    return TextResponse(result=diff)


@app.post(
    "/diff",
    response_model=TextResponse,
    description="Get comparison between two branches or commits.",
)
def diff_target(request: GitDiffRequest):
    repo = get_repo(request.repo_path)
    diff = repo.git.diff(request.target)
    return TextResponse(result=diff)


@app.post(
    "/commit",
    response_model=TextResponse,
    description="Commit staged changes to the repository.",
)
def commit_changes(request: GitCommitRequest):
    repo = get_repo(request.repo_path)
    commit = repo.index.commit(request.message)
    return TextResponse(result=f"Committed changes with hash {commit.hexsha}")


@app.post("/add", response_model=TextResponse, description="Stage files for commit.")
def add_files(request: GitAddRequest):
    repo = get_repo(request.repo_path)
    repo.index.add(request.files)
    return TextResponse(result="Files staged successfully.")


@app.post(
    "/reset", response_model=TextResponse, description="Unstage all staged changes."
)
def reset_changes(request: GitResetRequest):
    repo = get_repo(request.repo_path)
    repo.index.reset()
    return TextResponse(result="All staged changes reset.")


@app.post(
    "/log",
    response_model=LogResponse,
    description="Get recent commit history of the repository.",
)
def get_log(request: GitLogRequest):
    repo = get_repo(request.repo_path)
    commits = [
        f"Commit: {commit.hexsha}\n"
        f"Author: {commit.author}\n"
        f"Date: {commit.authored_datetime}\n"
        f"Message: {commit.message.strip()}\n"
        for commit in repo.iter_commits(max_count=request.max_count)
    ]
    return LogResponse(commits=commits)


@app.post(
    "/create_branch", response_model=TextResponse, description="Create a new branch."
)
def create_branch(request: GitCreateBranchRequest):
    repo = get_repo(request.repo_path)
    if request.base_branch is None:
        base_branch = repo.active_branch
    else:
        base_branch = repo.refs[request.base_branch]
    repo.create_head(request.branch_name, base_branch)
    return TextResponse(
        result=f"Created branch '{request.branch_name}' from '{base_branch}'."
    )


@app.post(
    "/checkout", response_model=TextResponse, description="Checkout an existing branch."
)
def checkout_branch(request: GitCheckoutRequest):
    repo = get_repo(request.repo_path)
    repo.git.checkout(request.branch_name)
    return TextResponse(result=f"Switched to branch '{request.branch_name}'.")


@app.post(
    "/show",
    response_model=TextResponse,
    description="Show details and diff of a specific commit.",
)
def show_revision(request: GitShowRequest):
    repo = get_repo(request.repo_path)
    commit = repo.commit(request.revision)
    details = (
        f"Commit: {commit.hexsha}\n"
        f"Author: {commit.author}\n"
        f"Date: {commit.authored_datetime}\n"
        f"Message: {commit.message.strip()}\n"
    )
    diff = commit.diff(
        commit.parents[0] if commit.parents else git.NULL_TREE, create_patch=True
    )
    diff_text = "\n".join(d.diff.decode("utf-8") for d in diff)
    return TextResponse(result=details + "\n" + diff_text)


@app.post(
    "/init", response_model=TextResponse, description="Initialize a new Git repository."
)
def init_repo(request: GitInitRequest):
    try:
        repo = git.Repo.init(path=request.repo_path, mkdir=True)
        return TextResponse(
            result=f"Initialized empty Git repository at '{repo.git_dir}'"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
