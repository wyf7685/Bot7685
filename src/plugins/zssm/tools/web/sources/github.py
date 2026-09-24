import re
from typing import Any
from urllib.parse import urlsplit

from githubkit import GitHub
from githubkit.versions.latest.models import FullRepository

from ....http_transport import (
    InvalidHttpTargetError,
    ValidatedHttpTarget,
    validate_http_target,
)
from .base import BaseSourceAdapter, normalize_page_text, optional_metadata
from .contracts import ExtractedPage, SourceIO, SourceTarget, SpecializedPage

_OWNER_RE = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?")
_REPO_RE = re.compile(r"[A-Za-z0-9_.-]{1,100}")
_NUMBER_RE = re.compile(r"[1-9][0-9]{0,12}")
_SHA_RE = re.compile(r"[0-9a-fA-F]{7,40}")
_TAG_RE = re.compile(r"[A-Za-z0-9_.-]{1,128}")


class PrivateGitHubRepositoryError(RuntimeError):
    """Authenticated access must not expose a private repository to chat."""


class GitHubAdapter(BaseSourceAdapter):
    source_id = "github"

    def __init__(self, github: GitHub[Any]) -> None:
        self._github = github

    def recognize(self, target: ValidatedHttpTarget) -> SourceTarget | None:
        if target.scheme != "https" or target.hostname != "github.com":
            return None
        parts = urlsplit(target.url).path.strip("/").split("/")
        if len(parts) < 2:
            return None
        owner, repo = parts[:2]
        if not _OWNER_RE.fullmatch(owner) or not _REPO_RE.fullmatch(repo):
            return None
        if repo in {".", ".."}:
            return None
        kind = "repository"
        reference = ""
        match parts[2:]:
            case []:
                pass
            case ["issues" | "pull", number] if _NUMBER_RE.fullmatch(number):
                kind, reference = parts[2], number
            case ["commit", sha] if _SHA_RE.fullmatch(sha):
                kind, reference = "commit", sha
            case ["releases", "tag", tag] if _TAG_RE.fullmatch(tag):
                kind, reference = "release", tag
            case _:
                return None
        suffix = (
            ""
            if kind == "repository"
            else f"/releases/tag/{reference}"
            if kind == "release"
            else f"/{kind}/{reference}"
        )
        canonical_url = f"https://github.com/{owner}/{repo}{suffix}"
        return SourceTarget(
            self.source_id, canonical_url, (owner, repo, kind, reference)
        )

    async def resolve_card_url(self, url: str, io: SourceIO) -> str | None:
        _ = io
        try:
            target = validate_http_target(url)
        except InvalidHttpTargetError:
            return None
        match = self.recognize(target)
        return match.canonical_url if match is not None else None

    async def fetch_specialized(
        self,
        target: SourceTarget,
        io: SourceIO,
    ) -> SpecializedPage | None:
        _ = io
        owner, repo, kind, reference = target.value
        repository = await self._github.rest.repos.async_get(owner, repo)
        if repository.parsed_data.private:
            raise PrivateGitHubRepositoryError
        if kind == "repository":
            extracted = _repository_page(repository.parsed_data)
        elif kind == "issues":
            issue = (
                await self._github.rest.issues.async_get(owner, repo, int(reference))
            ).parsed_data
            title = issue.title
            author = issue.user.login if issue.user else None
            extracted = _page(
                title,
                author,
                issue.created_at.isoformat(),
                f"State: {issue.state}",
                issue.body,
            )
        elif kind == "pull":
            pull = (
                await self._github.rest.pulls.async_get(owner, repo, int(reference))
            ).parsed_data
            extracted = _page(
                pull.title,
                pull.user.login,
                pull.created_at.isoformat(),
                f"State: {"merged" if pull.merged else pull.state}",
                pull.body,
            )
        elif kind == "commit":
            commit = (
                await self._github.rest.repos.async_get_commit(owner, repo, reference)
            ).parsed_data
            title = (
                commit.commit.message.splitlines()[0]
                if commit.commit.message
                else "Commit"
            )
            author = (
                commit.commit.author.name
                if commit.commit.author and isinstance(commit.commit.author.name, str)
                else None
            )
            extracted = _page(
                title,
                author,
                (
                    commit.commit.author.date.isoformat()
                    if commit.commit.author and commit.commit.author.date
                    else None
                ),
                f"Commit: {commit.sha}",
                commit.commit.message,
            )
        else:
            release = (
                await self._github.rest.repos.async_get_release_by_tag(
                    owner, repo, reference
                )
            ).parsed_data
            extracted = _page(
                release.name or release.tag_name,
                release.author.login,
                release.published_at.isoformat() if release.published_at else None,
                f"Tag: {release.tag_name}",
                release.body,
            )
        return SpecializedPage(target.canonical_url, extracted)


def _page(
    title: str,
    author: str | None,
    published: str | None,
    detail: str,
    body: object,
) -> ExtractedPage:
    normalized_title = optional_metadata(title, 500) or "GitHub item"
    content = body if isinstance(body, str) and body.strip() else normalized_title
    text = normalize_page_text(f"{detail}\n\n{content}")
    return ExtractedPage(normalized_title, author, "GitHub", published, None, text)


def _repository_page(repo: FullRepository) -> ExtractedPage:
    title = repo.full_name
    description = optional_metadata(repo.description, 4000)
    text = normalize_page_text(
        "\n".join(
            (
                f"Repository: {title}",
                f"Description: {description}" if description else "",
                f"Default branch: {repo.default_branch}",
                f"Language: {repo.language}" if repo.language else "",
                f"Stars: {repo.stargazers_count}; forks: {repo.forks_count}",
            )
        )
    )
    return ExtractedPage(title, None, "GitHub", None, None, text)


__all__ = ["GitHubAdapter", "PrivateGitHubRepositoryError"]
