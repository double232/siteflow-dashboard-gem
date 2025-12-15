from __future__ import annotations

import asyncio
import base64
import json
import re
import tempfile

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.config import get_settings
from app.services.ssh_client import SSHClientManager
from app.validators import (
    ValidationError,
    validate_site_name,
    validate_branch,
    validate_git_url,
    quote_shell_arg,
)


router = APIRouter(prefix="/api/deploy", tags=["deploy"])
settings = get_settings()
MAX_UPLOAD_SIZE = 100 * 1024 * 1024  # 100MB


class GitDeployRequest(BaseModel):
    site: str
    repo_url: str = Field(..., description="GitHub repo URL (https or git@)")
    branch: str = "main"


class DeployResponse(BaseModel):
    site: str
    status: str
    output: str
    repo_url: str | None = None


class PullRequest(BaseModel):
    site: str


def _get_ssh() -> SSHClientManager:
    return SSHClientManager(settings)


def _get_deploy_dir(ssh: SSHClientManager, site_path: str) -> str:
    """Determine the correct deploy directory based on docker-compose.yml."""
    try:
        compose = ssh.read_file(f"{site_path}/docker-compose.yml")
        # Static sites mount ./public, others mount ./app
        if "./public:" in compose or "./public/" in compose:
            return f"{site_path}/public"
        return f"{site_path}/app"
    except FileNotFoundError:
        return f"{site_path}/app"


def _normalize_repo_url(url: str) -> str:
    """Convert various GitHub URL formats to HTTPS clone URL."""
    # Handle git@ format
    if url.startswith("git@"):
        # git@github.com:user/repo.git -> https://github.com/user/repo.git
        match = re.match(r"git@([^:]+):(.+)", url)
        if match:
            host, path = match.groups()
            return f"https://{host}/{path}"

    # Handle browser URLs without .git
    if "github.com" in url and not url.endswith(".git"):
        url = url.rstrip("/") + ".git"

    return url


@router.post("/github", response_model=DeployResponse)
async def deploy_from_github(request: GitDeployRequest):
    """Deploy site content from a GitHub repository."""
    # Validate inputs
    try:
        validated_site = validate_site_name(request.site)
        validated_branch = validate_branch(request.branch)
        validated_url = validate_git_url(request.repo_url)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    ssh = _get_ssh()
    site_path = f"{settings.remote_sites_root}/{validated_site}"
    quoted_site_path = quote_shell_arg(site_path)

    # Check if site exists
    result = ssh.execute(f"test -d {quoted_site_path} && echo exists || echo missing")
    if "missing" in result.stdout:
        raise HTTPException(status_code=404, detail=f"Site '{validated_site}' not found")

    app_path = _get_deploy_dir(ssh, site_path)
    quoted_app_path = quote_shell_arg(app_path)
    quoted_url = quote_shell_arg(validated_url)
    quoted_branch = quote_shell_arg(validated_branch)

    # Check if already a git repo
    result = ssh.execute(f"test -d {quoted_app_path}/.git && echo git || echo empty")
    is_git = "git" in result.stdout

    outputs = []

    try:
        if is_git:
            # Pull latest
            result = await asyncio.to_thread(
                ssh.execute,
                f"cd {quoted_app_path} && git fetch origin && git reset --hard origin/{validated_branch}",
                check=False,
            )
        else:
            # Clone fresh
            result = await asyncio.to_thread(
                ssh.execute,
                f"rm -rf {quoted_app_path} && git clone --branch {quoted_branch} --depth 1 {quoted_url} {quoted_app_path}",
                check=False,
            )

        outputs.append(result.stdout or "")
        if result.stderr:
            outputs.append(result.stderr)

        if result.exit_code != 0:
            raise HTTPException(
                status_code=500,
                detail=f"Git operation failed: {result.stderr or result.stdout}",
            )

        # Save repo info for future pulls
        siteflow_config = {"repo_url": validated_url, "branch": validated_branch}
        config_json = json.dumps(siteflow_config)
        quoted_config = quote_shell_arg(config_json)
        ssh.execute(f"echo {quoted_config} > {quoted_site_path}/.siteflow.json", check=False)

        # Rebuild and restart containers
        result = await asyncio.to_thread(
            ssh.execute,
            f"cd {quoted_site_path} && docker compose down && docker compose build --no-cache && docker compose up -d",
            check=False,
        )
        outputs.append(result.stdout or "")
        if result.stderr:
            outputs.append(result.stderr)

        return DeployResponse(
            site=validated_site,
            status="success" if result.exit_code == 0 else "partial",
            output="\n".join(outputs),
            repo_url=validated_url,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/pull", response_model=DeployResponse)
async def pull_latest(request: PullRequest):
    """Pull latest changes from the configured repository."""
    # Validate site name
    try:
        validated_site = validate_site_name(request.site)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    ssh = _get_ssh()
    site_path = f"{settings.remote_sites_root}/{validated_site}"
    quoted_site_path = quote_shell_arg(site_path)

    # Check if site exists
    result = ssh.execute(f"test -d {quoted_site_path} && echo exists || echo missing")
    if "missing" in result.stdout:
        raise HTTPException(status_code=404, detail=f"Site '{validated_site}' not found")

    # Read siteflow config
    try:
        config_content = ssh.read_file(f"{site_path}/.siteflow.json")
        config = json.loads(config_content)
    except (FileNotFoundError, json.JSONDecodeError):
        raise HTTPException(
            status_code=400,
            detail="No deployment configured. Use 'Deploy from GitHub' first.",
        )

    # Validate branch from config
    branch = config.get("branch", "main")
    try:
        validated_branch = validate_branch(branch)
    except ValidationError:
        validated_branch = "main"  # Fallback to safe default

    app_path = _get_deploy_dir(ssh, site_path)
    quoted_app_path = quote_shell_arg(app_path)

    outputs = []

    # Pull latest
    result = await asyncio.to_thread(
        ssh.execute,
        f"cd {quoted_app_path} && git fetch origin && git reset --hard origin/{validated_branch}",
        check=False,
    )
    outputs.append(result.stdout or "")
    if result.stderr:
        outputs.append(result.stderr)

    if result.exit_code != 0:
        return DeployResponse(
            site=validated_site,
            status="error",
            output="\n".join(outputs),
            repo_url=config.get("repo_url"),
        )

    # Rebuild and restart
    result = await asyncio.to_thread(
        ssh.execute,
        f"cd {quoted_site_path} && docker compose down && docker compose build --no-cache && docker compose up -d",
        check=False,
    )
    outputs.append(result.stdout or "")
    if result.stderr:
        outputs.append(result.stderr)

    return DeployResponse(
        site=validated_site,
        status="success" if result.exit_code == 0 else "partial",
        output="\n".join(outputs),
        repo_url=config.get("repo_url"),
    )


@router.get("/{site}/status")
async def get_deploy_status(site: str):
    """Get deployment status for a site."""
    # Validate site name
    try:
        validated_site = validate_site_name(site)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    ssh = _get_ssh()
    site_path = f"{settings.remote_sites_root}/{validated_site}"
    quoted_site_path = quote_shell_arg(site_path)

    # Check if site exists
    result = ssh.execute(f"test -d {quoted_site_path} && echo exists || echo missing")
    if "missing" in result.stdout:
        raise HTTPException(status_code=404, detail=f"Site '{validated_site}' not found")

    # Read siteflow config
    try:
        config_content = ssh.read_file(f"{site_path}/.siteflow.json")
        config = json.loads(config_content)

        # Get last commit info
        app_path = f"{site_path}/app"
        quoted_app_path = quote_shell_arg(app_path)
        result = ssh.execute(
            f"cd {quoted_app_path} && git log -1 --format='%h %s (%ar)' 2>/dev/null || echo 'no commits'",
        )
        last_commit = result.stdout.strip()

        return {
            "site": validated_site,
            "configured": True,
            "repo_url": config.get("repo_url"),
            "branch": config.get("branch", "main"),
            "last_commit": last_commit,
        }
    except (FileNotFoundError, json.JSONDecodeError):
        return {
            "site": validated_site,
            "configured": False,
            "repo_url": None,
            "branch": None,
            "last_commit": None,
        }


@router.post("/upload", response_model=DeployResponse)
async def deploy_from_upload(
    site: str = Form(...),
    file: UploadFile = File(...),
):
    """Deploy site content from an uploaded zip file."""
    # Validate site name
    try:
        validated_site = validate_site_name(site)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    ssh = _get_ssh()
    site_path = f"{settings.remote_sites_root}/{validated_site}"
    quoted_site_path = quote_shell_arg(site_path)

    # Check if site exists
    result = ssh.execute(f"test -d {quoted_site_path} && echo exists || echo missing")
    if "missing" in result.stdout:
        raise HTTPException(status_code=404, detail=f"Site '{validated_site}' not found")

    # Validate file
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    if not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="Only .zip files are supported")

    # Read file content
    content = await file.read()
    if len(content) > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=400, detail="File too large (max 100MB)")

    outputs = []
    app_path = _get_deploy_dir(ssh, site_path)
    quoted_app_path = quote_shell_arg(app_path)

    try:
        # Base64 encode and transfer via SSH
        b64_content = base64.b64encode(content).decode("ascii")

        # Clear existing app directory and create fresh
        await asyncio.to_thread(
            ssh.execute,
            f"rm -rf {quoted_app_path} && mkdir -p {quoted_app_path}",
            check=True,
        )

        # Transfer zip file (split into chunks to avoid command line limits)
        remote_zip = f"/tmp/deploy_{validated_site}.zip"
        quoted_remote_zip = quote_shell_arg(remote_zip)
        chunk_size = 50000  # ~50KB chunks for base64

        # Write chunks
        for i in range(0, len(b64_content), chunk_size):
            chunk = b64_content[i : i + chunk_size]
            quoted_chunk = quote_shell_arg(chunk)
            op = ">>" if i > 0 else ">"
            await asyncio.to_thread(
                ssh.execute,
                f"echo {quoted_chunk} {op} {quoted_remote_zip}.b64",
                check=True,
            )

        # Decode and extract
        result = await asyncio.to_thread(
            ssh.execute,
            f"base64 -d {quoted_remote_zip}.b64 > {quoted_remote_zip} && unzip -o {quoted_remote_zip} -d {quoted_app_path} && rm -f {quoted_remote_zip} {quoted_remote_zip}.b64",
            check=False,
        )
        outputs.append(result.stdout or "")
        if result.stderr:
            outputs.append(result.stderr)

        if result.exit_code != 0:
            return DeployResponse(
                site=validated_site,
                status="error",
                output=f"Failed to extract zip: {result.stderr or result.stdout}",
                repo_url=None,
            )

        # Handle nested directory (if zip has a single root folder)
        result = await asyncio.to_thread(
            ssh.execute,
            f"cd {quoted_app_path} && if [ $(ls -1 | wc -l) -eq 1 ] && [ -d \"$(ls -1)\" ]; then mv $(ls -1)/* . 2>/dev/null; rmdir $(ls -d */ 2>/dev/null) 2>/dev/null; fi; echo done",
            check=False,
        )

        # Save deploy info
        siteflow_config = {"deploy_type": "upload", "filename": file.filename}
        config_json = json.dumps(siteflow_config)
        quoted_config = quote_shell_arg(config_json)
        ssh.execute(f"echo {quoted_config} > {quoted_site_path}/.siteflow.json", check=False)

        # Rebuild and restart containers
        result = await asyncio.to_thread(
            ssh.execute,
            f"cd {quoted_site_path} && docker compose down && docker compose build --no-cache && docker compose up -d",
            check=False,
        )
        outputs.append(result.stdout or "")
        if result.stderr:
            outputs.append(result.stderr)

        return DeployResponse(
            site=validated_site,
            status="success" if result.exit_code == 0 else "partial",
            output="\n".join(outputs),
            repo_url=None,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/folder", response_model=DeployResponse)
async def deploy_from_folder(
    site: str = Form(...),
    files: list[UploadFile] = File(...),
):
    """Deploy site content from uploaded folder files."""
    # Validate site name
    try:
        validated_site = validate_site_name(site)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    ssh = _get_ssh()
    site_path = f"{settings.remote_sites_root}/{validated_site}"
    quoted_site_path = quote_shell_arg(site_path)

    # Check if site exists
    result = ssh.execute(f"test -d {quoted_site_path} && echo exists || echo missing")
    if "missing" in result.stdout:
        raise HTTPException(status_code=404, detail=f"Site '{validated_site}' not found")

    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    outputs = []
    app_path = _get_deploy_dir(ssh, site_path)
    quoted_app_path = quote_shell_arg(app_path)

    try:
        # Clear existing directory
        await asyncio.to_thread(
            ssh.execute,
            f"rm -rf {quoted_app_path} && mkdir -p {quoted_app_path}",
            check=True,
        )

        file_count = 0
        for file in files:
            if not file.filename:
                continue

            # Get the relative path (browsers send webkitRelativePath as filename)
            rel_path = file.filename
            # Remove leading folder name if present (first segment)
            parts = rel_path.replace("\\", "/").split("/")
            if len(parts) > 1:
                rel_path = "/".join(parts[1:])  # Skip root folder

            # Sanitize path - reject traversal attempts
            if ".." in rel_path or rel_path.startswith("/"):
                continue

            remote_path = f"{app_path}/{rel_path}"
            quoted_remote_path = quote_shell_arg(remote_path)
            remote_dir = "/".join(remote_path.rsplit("/", 1)[:-1])
            quoted_remote_dir = quote_shell_arg(remote_dir)

            # Create directory if needed
            if remote_dir:
                await asyncio.to_thread(
                    ssh.execute,
                    f"mkdir -p {quoted_remote_dir}",
                    check=False,
                )

            # Read and transfer file
            content = await file.read()
            if len(content) > MAX_UPLOAD_SIZE:
                continue  # Skip files that are too large

            b64_content = base64.b64encode(content).decode("ascii")

            # Write file in chunks
            chunk_size = 50000
            remote_tmp = f"/tmp/upload_{validated_site}_{file_count}.b64"
            quoted_remote_tmp = quote_shell_arg(remote_tmp)

            for i in range(0, len(b64_content), chunk_size):
                chunk = b64_content[i : i + chunk_size]
                quoted_chunk = quote_shell_arg(chunk)
                op = ">>" if i > 0 else ">"
                await asyncio.to_thread(
                    ssh.execute,
                    f"echo {quoted_chunk} {op} {quoted_remote_tmp}",
                    check=False,
                )

            # Decode to final location
            await asyncio.to_thread(
                ssh.execute,
                f"base64 -d {quoted_remote_tmp} > {quoted_remote_path} && rm -f {quoted_remote_tmp}",
                check=False,
            )
            file_count += 1

        outputs.append(f"Uploaded {file_count} files")

        # Save deploy info
        siteflow_config = {"deploy_type": "folder", "file_count": file_count}
        config_json = json.dumps(siteflow_config)
        quoted_config = quote_shell_arg(config_json)
        ssh.execute(f"echo {quoted_config} > {quoted_site_path}/.siteflow.json", check=False)

        # Rebuild and restart containers
        result = await asyncio.to_thread(
            ssh.execute,
            f"cd {quoted_site_path} && docker compose down && docker compose build --no-cache && docker compose up -d",
            check=False,
        )
        outputs.append(result.stdout or "")
        if result.stderr:
            outputs.append(result.stderr)

        return DeployResponse(
            site=validated_site,
            status="success" if result.exit_code == 0 else "partial",
            output="\n".join(outputs),
            repo_url=None,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
