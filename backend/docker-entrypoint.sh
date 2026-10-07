#!/bin/sh
set -e

if [ -d /home/narmgr/.ssh ]; then
    for f in /home/narmgr/.ssh/id_*; do
        [ -f "$f" ] || continue
        bn=$(basename "$f")
        cp "$f" /tmp/
        chown narmgr:narmgr "/tmp/$bn"
        chmod 600 "/tmp/$bn"
        rm -f "/home/narmgr/.ssh/$bn"
        cp "/tmp/$bn" /home/narmgr/.ssh/
        chown narmgr:narmgr "/home/narmgr/.ssh/$bn"
    done
fi

exec su -s /bin/sh narmgr -c "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"
