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
    ssh = _get_ssh()
    site_path = f"{settings.remote_sites_root}/{request.site}"

    # Check if site exists
    result = ssh.execute(f"test -d {site_path} && echo exists || echo missing")
    if "missing" in result.stdout:
        raise HTTPException(status_code=404, detail=f"Site '{request.site}' not found")

    repo_url = _normalize_repo_url(request.repo_url)
    app_path = _get_deploy_dir(ssh, site_path)

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
    app_path = _get_deploy_dir(ssh, site_path)

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


@router.post("/upload", response_model=DeployResponse)
async def deploy_from_upload(
    site: str = Form(...),
    file: UploadFile = File(...),
):
    """Deploy site content from an uploaded zip file."""
    ssh = _get_ssh()
    site_path = f"{settings.remote_sites_root}/{site}"

    # Check if site exists
    result = ssh.execute(f"test -d {site_path} && echo exists || echo missing")
    if "missing" in result.stdout:
        raise HTTPException(status_code=404, detail=f"Site '{site}' not found")

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

    try:
        # Base64 encode and transfer via SSH
        b64_content = base64.b64encode(content).decode("ascii")

        # Clear existing app directory and create fresh
        await asyncio.to_thread(
            ssh.execute,
            f"rm -rf {app_path} && mkdir -p {app_path}",
            check=True,
        )

        # Transfer zip file (split into chunks to avoid command line limits)
        remote_zip = f"/tmp/deploy_{site}.zip"
        chunk_size = 50000  # ~50KB chunks for base64

        # Write chunks
        for i in range(0, len(b64_content), chunk_size):
            chunk = b64_content[i : i + chunk_size]
            op = ">>" if i > 0 else ">"
            await asyncio.to_thread(
                ssh.execute,
                f"echo '{chunk}' {op} {remote_zip}.b64",
                check=True,
            )

        # Decode and extract
        result = await asyncio.to_thread(
            ssh.execute,
            f"base64 -d {remote_zip}.b64 > {remote_zip} && unzip -o {remote_zip} -d {app_path} && rm -f {remote_zip} {remote_zip}.b64",
            check=False,
        )
        outputs.append(result.stdout or "")
        if result.stderr:
            outputs.append(result.stderr)

        if result.exit_code != 0:
            return DeployResponse(
                site=site,
                status="error",
                output=f"Failed to extract zip: {result.stderr or result.stdout}",
                repo_url=None,
            )

        # Handle nested directory (if zip has a single root folder)
        result = await asyncio.to_thread(
            ssh.execute,
            f"cd {app_path} && if [ $(ls -1 | wc -l) -eq 1 ] && [ -d \"$(ls -1)\" ]; then mv $(ls -1)/* . 2>/dev/null; rmdir $(ls -d */ 2>/dev/null) 2>/dev/null; fi; echo done",
            check=False,
        )

        # Save deploy info
        siteflow_config = {"deploy_type": "upload", "filename": file.filename}
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
            site=site,
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
    ssh = _get_ssh()
    site_path = f"{settings.remote_sites_root}/{site}"

    # Check if site exists
    result = ssh.execute(f"test -d {site_path} && echo exists || echo missing")
    if "missing" in result.stdout:
        raise HTTPException(status_code=404, detail=f"Site '{site}' not found")

    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    outputs = []
    app_path = _get_deploy_dir(ssh, site_path)

    try:
        # Clear existing directory
        await asyncio.to_thread(
            ssh.execute,
            f"rm -rf {app_path} && mkdir -p {app_path}",
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

            remote_path = f"{app_path}/{rel_path}"
            remote_dir = "/".join(remote_path.rsplit("/", 1)[:-1])

            # Create directory if needed
            if remote_dir:
                await asyncio.to_thread(
                    ssh.execute,
                    f"mkdir -p '{remote_dir}'",
                    check=False,
                )

            # Read and transfer file
            content = await file.read()
            if len(content) > MAX_UPLOAD_SIZE:
                continue  # Skip files that are too large

            b64_content = base64.b64encode(content).decode("ascii")

            # Write file in chunks
            chunk_size = 50000
            remote_tmp = f"/tmp/upload_{site}_{file_count}.b64"

            for i in range(0, len(b64_content), chunk_size):
                chunk = b64_content[i : i + chunk_size]
                op = ">>" if i > 0 else ">"
                await asyncio.to_thread(
                    ssh.execute,
                    f"echo '{chunk}' {op} {remote_tmp}",
                    check=False,
                )

            # Decode to final location
            await asyncio.to_thread(
                ssh.execute,
                f"base64 -d {remote_tmp} > '{remote_path}' && rm -f {remote_tmp}",
                check=False,
            )
            file_count += 1

        outputs.append(f"Uploaded {file_count} files")

        # Save deploy info
        siteflow_config = {"deploy_type": "folder", "file_count": file_count}
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
            site=site,
            status="success" if result.exit_code == 0 else "partial",
            output="\n".join(outputs),
            repo_url=None,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
