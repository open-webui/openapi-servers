from fastapi import FastAPI, HTTPException, Body
from fastapi.responses import PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware


from pydantic import BaseModel, Field
import os
import pathlib
import asyncio
from typing import List, Optional, Literal
import difflib

app = FastAPI(
    title="Secure Filesystem API",
    version="0.1.0",
    description="A secure file manipulation server for reading, editing, writing, listing, and searching files with access restrictions.",
)

origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Constants
ALLOWED_DIRECTORIES = [
    str(pathlib.Path(os.path.expanduser("~/mydir")).resolve())
]  # 👈 Replace with your paths

# ------------------------------------------------------------------------------
# Utility functions
# ------------------------------------------------------------------------------


def normalize_path(requested_path: str) -> pathlib.Path:
    requested = pathlib.Path(os.path.expanduser(requested_path)).resolve()
    for allowed in ALLOWED_DIRECTORIES:
        if str(requested).startswith(allowed):
            return requested
    raise HTTPException(
        status_code=403,
        detail=f"Access denied: {requested} is outside allowed directories.",
    )


# ------------------------------------------------------------------------------
# Pydantic Schemas
# ------------------------------------------------------------------------------


class ReadFileRequest(BaseModel):
    path: str = Field(..., description="Path to the file to read")


class WriteFileRequest(BaseModel):
    path: str = Field(
        ..., description="Path to write to. Existing file will be overwritten."
    )
    content: str = Field(..., description="UTF-8 encoded text content to write.")


class EditOperation(BaseModel):
    oldText: str = Field(
        ..., description="Text to find and replace (exact match required)"
    )
    newText: str = Field(..., description="Replacement text")


class EditFileRequest(BaseModel):
    path: str = Field(..., description="Path to the file to edit.")
    edits: List[EditOperation] = Field(..., description="List of edits to apply.")
    dryRun: bool = Field(
        False, description="If true, only return diff without modifying file."
    )


class CreateDirectoryRequest(BaseModel):
    path: str = Field(
        ...,
        description="Directory path to create. Intermediate dirs are created automatically.",
    )


class ListDirectoryRequest(BaseModel):
    path: str = Field(..., description="Directory path to list contents for.")


class DirectoryTreeRequest(BaseModel):
    path: str = Field(
        ..., description="Directory path for which to return recursive tree."
    )


class SearchFilesRequest(BaseModel):
    path: str = Field(..., description="Base directory to search in.")
    pattern: str = Field(
        ..., description="Filename pattern (case-insensitive substring match)."
    )
    excludePatterns: Optional[List[str]] = Field(
        default=[], description="Patterns to exclude."
    )


# ------------------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------------------


@app.post("/read_file", response_class=PlainTextResponse, summary="Read a file")
async def read_file(data: ReadFileRequest = Body(...)):
    """
    Read the entire contents of a file.
    """
    path = normalize_path(data.path)
    try:
        return path.read_text(encoding="utf-8")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/write_file", response_class=PlainTextResponse, summary="Write to a file")
async def write_file(data: WriteFileRequest = Body(...)):
    """
    Write content to a file, overwriting if it exists.
    """
    path = normalize_path(data.path)
    try:
        path.write_text(data.content, encoding="utf-8")
        return f"Successfully wrote to {data.path}"
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post(
    "/edit_file", response_class=PlainTextResponse, summary="Edit a file with diff"
)
async def edit_file(data: EditFileRequest = Body(...)):
    """
    Apply a list of edits to a text file. Support dry-run to get unified diff.
    """
    path = normalize_path(data.path)
    original = path.read_text(encoding="utf-8")
    modified = original

    for edit in data.edits:
        if edit.oldText not in modified:
            raise HTTPException(
                status_code=400,
                detail=f"oldText not found in content: {edit.oldText[:50]}",
            )
        modified = modified.replace(edit.oldText, edit.newText, 1)

    if data.dryRun:
        diff = difflib.unified_diff(
            original.splitlines(keepends=True),
            modified.splitlines(keepends=True),
            fromfile="original",
            tofile="modified",
        )
        return "".join(diff)

    path.write_text(modified, encoding="utf-8")
    return f"Successfully edited file {data.path}"


@app.post(
    "/create_directory", response_class=PlainTextResponse, summary="Create a directory"
)
async def create_directory(data: CreateDirectoryRequest = Body(...)):
    """
    Create a new directory recursively.
    """
    dir_path = normalize_path(data.path)
    try:
        dir_path.mkdir(parents=True, exist_ok=True)
        return f"Successfully created directory {data.path}"
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post(
    "/list_directory", summary="List a directory"
)
async def list_directory(data: ListDirectoryRequest = Body(...)):
    """
    List contents of a directory.
    """
    dir_path = normalize_path(data.path)
    if not dir_path.is_dir():
        raise HTTPException(status_code=400, detail="Provided path is not a directory")

    listing = []
    for entry in dir_path.iterdir():
        entry_type = "directory" if entry.is_dir() else "file"
        listing.append({"name": entry.name, "type": entry_type})

    # Return the list directly, FastAPI will serialize it to JSON
    return listing


@app.post("/directory_tree", summary="Recursive directory tree")
async def directory_tree(data: DirectoryTreeRequest = Body(...)):
    """
    Recursively return a tree structure of a directory.
    """
    base_path = normalize_path(data.path)

    def build_tree(current: pathlib.Path):
        entries = []
        for item in current.iterdir():
            entry = {
                "name": item.name,
                "type": "directory" if item.is_dir() else "file",
            }
            if item.is_dir():
                entry["children"] = build_tree(item)
            entries.append(entry)
        return entries

    return build_tree(base_path)


@app.post("/search_files", summary="Search for files")
async def search_files(data: SearchFilesRequest = Body(...)):
    """
    Search files and directories matching a pattern.
    """
    base_path = normalize_path(data.path)
    results = []

    for root, dirs, files in os.walk(base_path):
        root_path = pathlib.Path(root)
        # Apply exclusion patterns
        excluded = False
        for pattern in data.excludePatterns:
            if pathlib.Path(root).match(pattern):
                excluded = True
                break
        if excluded:
            continue
        for item in files + dirs:
            if data.pattern.lower() in item.lower():
                result_path = root_path / item
                if any(str(result_path).startswith(alt) for alt in ALLOWED_DIRECTORIES):
                    results.append(str(result_path))

    return {"matches": results or ["No matches found"]}


@app.get("/list_allowed_directories", summary="List access-permitted directories")
async def list_allowed_directories():
    """
    Show all directories this server can access.
    """
    return {"allowed_directories": ALLOWED_DIRECTORIES}
