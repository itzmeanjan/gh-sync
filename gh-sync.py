#!/usr/bin/python

import asyncio
import argparse
import os
import subprocess
import sys
from gql import Client, gql
from gql.transport.aiohttp import AIOHTTPTransport
from dotenv import load_dotenv

load_dotenv()

GITHUB_GRAPHQL_ENDPOINT = "https://api.github.com/graphql"
GITHUB_API_TOKEN = os.getenv("GITHUB_API_TOKEN")
GIT_TIMEOUT = 300  # 5 minutes timeout per repo

GITHUB_GRAPHQL_QUERY = """
query {
    viewer {
        repositories(first: 100, after: END_CURSOR, affiliations: [OWNER], ownerAffiliations:[OWNER]) {
            totalCount
            pageInfo {
                endCursor
                hasNextPage
            }
            nodes {
                name
                url
            }
        }
    }
}
"""


async def fetch_repositories(client: Client) -> list[dict[str, str]]:
    repositories = []
    end_cursor = "null"

    async with client as session:
        while True:
            query_str = GITHUB_GRAPHQL_QUERY.replace("END_CURSOR", end_cursor)
            query = gql(query_str)
            result = await session.execute(query)

            repos_data = result["viewer"]["repositories"]
            num_total_repos = repos_data["totalCount"]
            has_more_repos = repos_data["pageInfo"]["hasNextPage"]
            cursor = repos_data["pageInfo"]["endCursor"]

            for node in repos_data["nodes"]:
                if node:
                    repositories.append({"name": node["name"], "url": node["url"]})

            print(f"Fetched {len(repositories)}/{num_total_repos} GitHub Repositories", flush=True)

            if not has_more_repos:
                break

            end_cursor = f'"{cursor}"'

    return repositories


async def sync_repository(target_dir: str, repo_name: str, repo_url: str, semaphore: asyncio.Semaphore) -> str | None:
    async with semaphore:
        local_path = os.path.abspath(os.path.join(target_dir, repo_name))

        stdout = subprocess.DEVNULL
        stderr = subprocess.DEVNULL

        env = os.environ.copy()
        env["GIT_TERMINAL_PROMPT"] = "0"

        try:
            if os.path.exists(local_path):
                if os.path.isdir(os.path.join(local_path, ".git")):
                    print(f"Updating {repo_name}...", flush=True)
                    # 1. Fetch all branches, tags and prune deleted remote branches
                    process = await asyncio.create_subprocess_exec(
                        "git",
                        "fetch",
                        "--all",
                        "--prune",
                        "--tags",
                        cwd=local_path,
                        stdout=stdout,
                        stderr=stderr,
                        env=env,
                    )
                    try:
                        await asyncio.wait_for(process.wait(), timeout=GIT_TIMEOUT)
                    except asyncio.TimeoutError:
                        try:
                            process.terminate()
                        except:
                            pass
                        return f"Timeout fetching {repo_name} (>{GIT_TIMEOUT}s)"

                    if process.returncode != 0:
                        return f"Error fetching {repo_name}: git fetch exited with {process.returncode}"

                    # 2. Pull changes for the current branch (fast-forward only)
                    process = await asyncio.create_subprocess_exec(
                        "git", "pull", "--ff-only", cwd=local_path, stdout=stdout, stderr=stderr, env=env
                    )
                    try:
                        await asyncio.wait_for(process.wait(), timeout=GIT_TIMEOUT)
                    except asyncio.TimeoutError:
                        try:
                            process.terminate()
                        except:
                            pass
                        return f"Timeout pulling {repo_name} (>{GIT_TIMEOUT}s)"

                    if process.returncode != 0:
                        return f"Error pulling {repo_name}: git pull exited with {process.returncode}"

                    # 3. Update submodules recursively
                    process = await asyncio.create_subprocess_exec(
                        "git",
                        "submodule",
                        "update",
                        "--init",
                        "--recursive",
                        cwd=local_path,
                        stdout=stdout,
                        stderr=stderr,
                        env=env,
                    )
                    try:
                        await asyncio.wait_for(process.wait(), timeout=GIT_TIMEOUT)
                    except asyncio.TimeoutError:
                        try:
                            process.terminate()
                        except:
                            pass
                        return f"Timeout updating submodules for {repo_name} (>{GIT_TIMEOUT}s)"

                    if process.returncode != 0:
                        return f"Error updating submodules for {repo_name}: git submodule update exited with {process.returncode}"
                else:
                    return f"Skipping {repo_name}: Directory exists but is not a git repository."
            else:
                print(f"Cloning {repo_name}...", flush=True)
                process = await asyncio.create_subprocess_exec(
                    "git", "clone", "--recursive", repo_url, local_path, stdout=stdout, stderr=stderr, env=env
                )
                try:
                    await asyncio.wait_for(process.wait(), timeout=GIT_TIMEOUT)
                except asyncio.TimeoutError:
                    try:
                        process.terminate()
                    except:
                        pass
                    return f"Timeout cloning {repo_name} (>{GIT_TIMEOUT}s)"

                if process.returncode != 0:
                    return f"Error cloning {repo_name}: git clone exited with {process.returncode}"
        except asyncio.CancelledError:
            if "process" in locals() and process.returncode is None:
                try:
                    process.terminate()
                    await process.wait()
                except ProcessLookupError:
                    pass
            raise
        except Exception as e:
            return f"Unexpected error with {repo_name}: {e}"

        return None


async def main() -> None:
    parser = argparse.ArgumentParser(description="Synchronize GitHub repositories to a local directory.")
    parser.add_argument("target_directory", help="The directory where repositories should be synced.")
    args = parser.parse_args()

    target_dir = os.path.abspath(args.target_directory)
    if not os.path.exists(target_dir):
        os.makedirs(target_dir, exist_ok=True)
        print(f"Created target directory: {target_dir}", flush=True)

    if not GITHUB_API_TOKEN:
        print("Error: GITHUB_API_TOKEN not found in environment variables or .env file.", file=sys.stderr)
        print("Please create a .env file based on .env.example and add your token.", file=sys.stderr)

        sys.exit(1)

    transport = AIOHTTPTransport(url=GITHUB_GRAPHQL_ENDPOINT, headers={"Authorization": f"bearer {GITHUB_API_TOKEN}"})
    client = Client(transport=transport, fetch_schema_from_transport=True)

    try:
        repos = await fetch_repositories(client)
    except Exception as e:
        print(f"Failed to fetch repositories: {e}", flush=True)
        sys.exit(1)

    print(f"Comparing and syncing {len(repos)} repositories in parallel...", flush=True)

    concurrency_limit = (os.cpu_count() or 1) * 2
    semaphore = asyncio.Semaphore(concurrency_limit)

    tasks = [sync_repository(target_dir, repo["name"], repo["url"], semaphore) for repo in repos]
    results = await asyncio.gather(*tasks)

    failures = [r for r in results if r is not None]

    print("-" * 20, flush=True)
    if failures:
        print(f"Synchronization finished with {len(failures)} failures:", flush=True)
        for error in failures:
            print(f"  - {error}", flush=True)
        sys.exit(1)
    else:
        print("Synchronization complete. All repositories updated successfully.", flush=True)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nInterrupted by user. Shutting down...", flush=True)
        sys.exit(0)
