# Publish the cleaned RoadGuard AI project to GitHub

## Before the first push

- Keep the GitHub repository **private** until you finish testing.
- Never add `.env`, a Firebase service-account JSON file, `roadguard.db`, or
  personal research CSV files.
- This cleaned package already ignores those files. Verify before every push.

## Commands

Open a new VS Code terminal inside the extracted project folder. Replace
`YOUR-USERNAME` with your GitHub username after creating an empty private
repository named `RoadGuard-AI` on GitHub.

```powershell
git init
git branch -M main
git status
git add .
git status
git commit -m "Initial secure RoadGuard AI prototype"
git remote add origin https://github.com/YOUR-USERNAME/RoadGuard-AI.git
git push -u origin main
```

At the second `git status`, confirm that these are **not** listed:

```text
.env
*.json service-account key
roadguard.db
datasets/*.csv
backups/
```

If a private file appears, remove it from staging before committing:

```powershell
git restore --staged path/to/file
```

Do not put a GitHub password, Firebase private key, or service-account JSON in
the repository. GitHub sign-in should occur through its normal browser prompt.
