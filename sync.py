#!/usr/bin/python

import asyncio
import argparse
import os
import subprocess
import sys
from gql import Client, gql
from gql.transport.aiohttp import AIOHTTPTransport

GITHUB_GRAPHQL_ENDPOINT = "https://api.github.com/graphql"
GITHUB_API_TOKEN = "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"

GITHUB_GRAPHQL_QUERY = """
query {
    viewer {
        repositories(first: 100, after: END_CURSOR, affiliations: [OWNER, COLLABORATOR, ORGANIZATION_MEMBER], ownerAffiliations:[OWNER, ORGANIZATION_MEMBER, COLLABORATOR]) {
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
                    repositories.append({
                        "name": node["name"],
                        "url": node["url"]
                    })

            print(f"Fetched {len(repositories)}/{num_total_repos} GitHub Repositories", flush=True)

            if not has_more_repos:
                break
            
            end_cursor = f'"{cursor}"'

    return repositories

async def sync_repository(target_dir: str, repo_name: str, repo_url: str, verbose: bool, semaphore: asyncio.Semaphore) -> None:
    async with semaphore:
        local_path = os.path.abspath(os.path.join(target_dir, repo_name))
        
        # Setup stdout/stderr based on verbose flag
        stdout = None if verbose else subprocess.DEVNULL
        stderr = None if verbose else subprocess.DEVNULL

        if os.path.exists(local_path):
            if os.path.isdir(os.path.join(local_path, ".git")):
                print(f"Updating {repo_name}...", flush=True)
                try:
                    # Using asyncio.to_thread for blocking subprocess.run
                    await asyncio.to_thread(
                        subprocess.run,
                        ["git", "pull"],
                        cwd=local_path,
                        check=True,
                        stdout=stdout,
                        stderr=stderr
                    )
                except subprocess.CalledProcessError as e:
                    print(f"Error updating {repo_name}: {e}", flush=True)
            else:
                print(f"Skipping {repo_name}: Directory exists but is not a git repository.", flush=True)
        else:
            print(f"Cloning {repo_name}...", flush=True)
            try:
                await asyncio.to_thread(
                    subprocess.run,
                    ["git", "clone", repo_url, local_path],
                    check=True,
                    stdout=stdout,
                    stderr=stderr
                )
            except subprocess.CalledProcessError as e:
                print(f"Error cloning {repo_name}: {e}", flush=True)

async def main() -> None:
    parser = argparse.ArgumentParser(description="Synchronize GitHub repositories to a local directory.")
    parser.add_argument("target_directory", help="The directory where repositories should be synced.")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show git output.")
    args = parser.parse_args()

    target_dir = os.path.abspath(args.target_directory)
    if not os.path.exists(target_dir):
        os.makedirs(target_dir, exist_ok=True)
        print(f"Created target directory: {target_dir}", flush=True)

    transport = AIOHTTPTransport(url=GITHUB_GRAPHQL_ENDPOINT, headers={'Authorization': f'bearer {GITHUB_API_TOKEN}'})
    client = Client(transport=transport, fetch_schema_from_transport=True)

    try:
        repos = await fetch_repositories(client)
    except Exception as e:
        print(f"Failed to fetch repositories: {e}", flush=True)
        sys.exit(1)

    print(f"Comparing and syncing {len(repos)} repositories in parallel...", flush=True)

    concurrency_limit = (os.cpu_count() or 1) * 2
    semaphore = asyncio.Semaphore(concurrency_limit)
    
    tasks = [
        sync_repository(target_dir, repo["name"], repo["url"], args.verbose, semaphore)
        for repo in repos
    ]
    await asyncio.gather(*tasks)

    print("Synchronization complete.", flush=True)

if __name__ == '__main__':
    asyncio.run(main())
