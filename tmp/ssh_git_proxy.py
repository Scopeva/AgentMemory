#!/usr/bin/env python3
"""Minimal SSH transport proxy for git.

Usage (as GIT_SSH_COMMAND):
    python /tmp/ssh_git_proxy.py ssh -T git@github.com ...

git will invoke this in place of the real `ssh` binary. We forward all
subprocess-level git commands (clone/fetch/push) through a paramiko
connection using the sandbox's private key.
"""
import os, sys, threading

import paramiko

KEY = os.path.expanduser("~/.ssh/id_ed25519_sandbox")

def _open_connection(host):
    key = paramiko.Ed25519Key.from_private_key_file(KEY)
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(host, port=22, username="git", pkey=key, timeout=30)
    return client

def main():
    args = sys.argv[1:]
    # expected: args[0] == "ssh"; look for "git@host" among args
    host = None
    for a in args:
        if a.startswith("git@"):
            host = a.split("@", 1)[1]
            break
    if host is None:
        print("cannot parse host", file=sys.stderr)
        sys.exit(2)

    # Determine which git command to run: the last arg that is not a host
    # git passes the command as the final argument, e.g.
    #   ssh -T git@github.com git-upload-pack '/Repo.git'
    # or for push:
    #   ssh -T git@github.com git-receive-pack '/Repo.git'
    cmd_args = args[args.index(host)+1:]
    if not cmd_args:
        print("no command found", file=sys.stderr)
        sys.exit(2)
    remote_cmd = " ".join(shlex.quote(a) for a in cmd_args)
    import shlex
    remote_cmd = " ".join(shlex.quote(a) for a in cmd_args)

    client = _open_connection(host)
    chan = client.get_transport().open_session()
    chan.exec_(remote_cmd)

    # Bidirectional copy between local stdin/stdout and the channel
    # (in git's case, the data flows through the subprocess pipes).
    # paramiko channels aren't selectable with select(), so we thread them.
    done = threading.Event()
    def send_thread():
        try:
            while not done.is_set():
                data = os.read(0, 65536)
                if not data:
                    break
                chan.sendall(data)
            chan.shutdown_write()
        except Exception:
            pass
        finally:
            done.set()

    t = threading.Thread(target=send_thread, daemon=True)
    t.start()

    while True:
        data = chan.recv(65536)
        if not data:
            break
        os.write(1, data)
    chan.close()
    client.close()
    rc = chan.get_exit_status() or 0
    sys.exit(rc)

if __name__ == "__main__":
    main()
