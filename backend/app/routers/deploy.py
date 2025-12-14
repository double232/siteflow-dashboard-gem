from __future__ import annotations

import asyncio
import json
import re

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.config import get_settings
from app.services.ssh_client import SSHClientManager


router = APIRouter(prefix="/api/deploy", tags=["deploy"])
settings = get_settings()


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
    ssh = _get_ssh()
    site_path = f"{settings.remote_sites_root}/{request.site}"

    # Check if site exists
    result = ssh.execute(f"test -d {site_path} && echo exists || echo missing")
    if "missing" in result.stdout:
        raise HTTPException(status_code=404, detail=f"Site '{request.site}' not found")

    repo_url = _normalize_repo_url(request.repo_url)
    app_path = f"{site_path}/app"

    # Check if already a git repo
    result = ssh.execute(f"test -d {app_path}/.git && echo git || echo empty")
    is_git = "git" in result.stdout

    outputs = []

    try:
        if is_git:
            # Pull latest
            result = await asyncio.to_thread(
                ssh.execute,
                f"cd {app_path} && git fetch origin && git reset --hard origin/{request.branch}",
                check=False,
            )
        else:
            # Clone fresh
            result = await asyncio.to_thread(
                ssh.execute,
                f"rm -rf {app_path} && git clone --branch {request.branch} --depth 1 {repo_url} {app_path}",
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
        siteflow_config = {"repo_url": repo_url, "branch": request.branch}
        config_json = json.dumps(siteflow_config)
        ssh.execute(f"echo '{config_json}' > {site_path}/.siteflow.json", check=False)

        # Rebuild and restart containers
        result = await asyncio.to_thread(
            ssh.execute,
            f"cd {site_path} && docker compose down && docker compose build --no-cache && docker compose up -d",
            check=False,
        )
        outputs.append(result.stdout or "")
        if result.stderr:
            outputs.append(result.stderr)

        return DeployResponse(
            site=request.site,
            status="success" if result.exit_code == 0 else "partial",
            output="\n".join(outputs),
            repo_url=repo_url,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/pull", response_model=DeployResponse)
async def pull_latest(request: PullRequest):
    """Pull latest changes from the configured repository."""
    ssh = _get_ssh()
    site_path = f"{settings.remote_sites_root}/{request.site}"

    # Check if site exists
    result = ssh.execute(f"test -d {site_path} && echo exists || echo missing")
    if "missing" in result.stdout:
        raise HTTPException(status_code=404, detail=f"Site '{request.site}' not found")

    # Read siteflow config
    try:
        config_content = ssh.read_file(f"{site_path}/.siteflow.json")
        config = json.loads(config_content)
    except (FileNotFoundError, json.JSONDecodeError):
        raise HTTPException(
            status_code=400,
            detail="No deployment configured. Use 'Deploy from GitHub' first.",
        )

    branch = config.get("branch", "main")
    app_path = f"{site_path}/app"

    outputs = []

    # Pull latest
    result = await asyncio.to_thread(
        ssh.execute,
        f"cd {app_path} && git fetch origin && git reset --hard origin/{branch}",
        check=False,
    )
    outputs.append(result.stdout or "")
    if result.stderr:
        outputs.append(result.stderr)

    if result.exit_code != 0:
        return DeployResponse(
            site=request.site,
            status="error",
            output="\n".join(outputs),
            repo_url=config.get("repo_url"),
        )

    # Rebuild and restart
    result = await asyncio.to_thread(
        ssh.execute,
        f"cd {site_path} && docker compose down && docker compose build --no-cache && docker compose up -d",
        check=False,
    )
    outputs.append(result.stdout or "")
    if result.stderr:
        outputs.append(result.stderr)

    return DeployResponse(
        site=request.site,
        status="success" if result.exit_code == 0 else "partial",
        output="\n".join(outputs),
        repo_url=config.get("repo_url"),
    )


@router.get("/{site}/status")
async def get_deploy_status(site: str):
    """Get deployment status for a site."""
    ssh = _get_ssh()
    site_path = f"{settings.remote_sites_root}/{site}"

    # Check if site exists
    result = ssh.execute(f"test -d {site_path} && echo exists || echo missing")
    if "missing" in result.stdout:
        raise HTTPException(status_code=404, detail=f"Site '{site}' not found")

    # Read siteflow config
    try:
        config_content = ssh.read_file(f"{site_path}/.siteflow.json")
        config = json.loads(config_content)

        # Get last commit info
        app_path = f"{site_path}/app"
        result = ssh.execute(
            f"cd {app_path} && git log -1 --format='%h %s (%ar)' 2>/dev/null || echo 'no commits'",
        )
        last_commit = result.stdout.strip()

        return {
            "site": site,
            "configured": True,
            "repo_url": config.get("repo_url"),
            "branch": config.get("branch", "main"),
            "last_commit": last_commit,
        }
    except (FileNotFoundError, json.JSONDecodeError):
        return {
            "site": site,
            "configured": False,
            "repo_url": None,
            "branch": None,
            "last_commit": None,
        }
