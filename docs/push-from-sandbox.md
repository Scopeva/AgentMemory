# Pushing from the sandbox to GitHub

The sandbox has no `ssh` binary, so git uses a Python/paramiko SSH proxy
(`tmp/ssh_git_proxy.py`). Authentication requires your Ed25519 **private key**
to exist at a known path and the matching **public key** to be registered on
GitHub.

## Per-use key (recommended — short-lived)

1. **Local**: generate a dedicated key
   ```bash
   ssh-keygen -t ed25519 -C agent-memory-sandbox -f ~/.ssh/id_ed25519_sandbox -N ""
   ```
2. **Local**: add the public key to GitHub (repo deploy key or account-level):
   https://github.com/Scopeva/AgentMemory/keys
3. **Sandbox**: drop the private key where the proxy can find it:
   ```bash
   # from the local machine, into the sandbox's ~/.ssh/
   cat ~/.ssh/id_ed25519_sandbox   # paste into sandbox ~/.ssh/id_ed25519_sandbox
   ```
4. **Sandbox**: push
   ```bash
   export GIT_SSH_COMMAND="python3 tmp/ssh_git_proxy.py ssh"
   git push origin master
   ```
   or the helper:
   ```bash
   ./scripts/push.sh
   ```
5. **Local + GitHub**: when done, remove the public key from GitHub
   and delete `~/.ssh/id_ed25519_sandbox` (local + sandbox) to close the window.

## Alternative: HTTPS + fine-grained PAT (no key needed in sandbox)

```bash
git remote set-url origin https://github.com/Scopeva/AgentMemory.git
# push with a short-lived fine-grained PAT scoped to this repo only
git push origin master   # prompt for token, or embed: https://x-access-token:<PAT>@github.com/...
```

This is the lower-risk option: the PAT can be 1-day expiry, repo-scoped, and
instantly revoked without touching SSH key management.
