# fetch-gh-repos

A Python script to synchronize all your personal GitHub repositories to a local directory, concurrently.

## Description

This tool automates the process of cloning and updating local copies of your GitHub repositories. It uses the GitHub GraphQL API to fetch a list of all repositories you own and then uses `git` to synchronize them locally.

## Prerequisites

- Python 3.10+
- Git
- GitHub Personal Access Token (PAT), with `repository metadata reading` permission

## Setup

1. Clone this repository.
2. Create a `.env` file from the template:

```bash
cp .env.example .env
```

3. Edit `.env` and add your [GitHub Personal Access Token](https://github.com/settings/personal-access-tokens).
4. Setup the environment.

```bash
make setup
```

## Usage

1. Run the synchronization. Activate the Python virtual environment and run the script, providing a target directory. I generally keep a local copy of my work in an external SSD. From time to time I run this script to keep local copy of my work up-to-date.

```bash
source .venv/bin/activate
python sync.py /path/to/your/local/repos
```

## Development

- Source formatting with `make format`.
- Cleanup Python virtual environment setup with `make clean`.
