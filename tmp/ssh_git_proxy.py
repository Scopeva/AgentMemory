#!/usr/bin/env python3
"""GIT_SSH_COMMAND proxy: forward git's ssh calls through paramiko.

git invokes this instead of the missing `ssh` binary. It reads the
sandbox's Ed25519 private key, opens a paramiko connection to GitHub,
runs the requested git remote command (e.g. git-receive-pack), and
streams data bidirectionally between local stdin/stdout and the
remote channel.

Env:
    SSH_PROXY_KEY   path to the Ed25519 private key (default: ~/.ssh/id_ed25519_sandbox)
    SSH_PROXY_DEBUG if set, print diagnostics to stderr
"""
import os, sys, shlex, threading

import paramiko

def main() -> int:
    args = sys.argv[1:]
    # git passes: ssh [-T] git@host git-receive-pack '/Owner/repo.git'
    host = None
    for i, a in enumerate(args):
        if a.startswith("git@"):
            host = a.split("@", 1)[1]
            cmd_args = args[i + 1:]
            break
    if host is None:
        print("ssh_git_proxy: no git@host argument found", file=sys.stderr)
        return 2
    if not cmd_args:
        print("ssh_git_proxy: no remote command found", file=sys.stderr)
        return 2

    # join with spaces; GitHub's remote-side sshd handles quoting on its end
    remote_cmd = " ".join(cmd_args)
    debug = os.environ.get("SSH_PROXY_DEBUG")
    if debug:
        print(f"[ssh_git_proxy] exec: {remote_cmd}", file=sys.stderr)

    key_path = os.environ.get(
        "SSH_PROXY_KEY",
        os.path.expanduser("~/.ssh/id_ed25519_sandbox"),
    )
    key = paramiko.Ed25519Key.from_private_key_file(key_path)

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(host, port=22, username="git", pkey=key, timeout=30)

    chan = client.get_transport().open_session()
    chan.exec_command(remote_cmd)
    if debug:
        print(f"[ssh_git_proxy] channel opened for {remote_cmd}", file=sys.stderr)

    def pump_to_remote():
        try:
            while True:
                data = os.read(0, 65536)
                if not data:
                    break
                chan.sendall(data)
            chan.shutdown_write()
        except (OSError, EOFError):
            pass
        except Exception as e:
            if debug:
                print(f"[ssh_git_proxy] send error: {e}", file=sys.stderr)

    t = threading.Thread(target=pump_to_remote, daemon=True)
    t.start()

    out = os.fdopen(1, "wb", closefd=False)
    err = os.fdopen(2, "wb", closefd=False)
    try:
        while True:
            data = chan.recv(65536)
            if not data:
                break
            out.write(data)
            out.flush()
            if chan.recv_stderr_ready():
                err_data = chan.recv_stderr(65536)
                err.write(b"[remote-stderr] " + err_data + b"\n")
                err.flush()
        while chan.recv_stderr_ready():
            err_data = chan.recv_stderr(65536)
            err.write(b"[remote-stderr] " + err_data + b"\n")
            err.flush()
    except (OSError, EOFError):
        pass
    finally:
        rc = chan.recv_exit_status()
        if debug:
            print(f"[ssh_git_proxy] remote exit status: {rc}", file=sys.stderr)
        client.close()
    return rc if rc is not None else 0

if __name__ == "__main__":
    sys.exit(main())
