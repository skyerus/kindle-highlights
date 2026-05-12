#!/bin/sh
# quote-saver.sh — tap-to-start wrapper for the quote screensaver daemon.
# Drop into /mnt/us/documents/ so sh_integration shows it as a tappable item.
# Idempotent: if the daemon is already running, just acknowledges and exits.

IMG=/mnt/us/linkss/screensavers/bg_ss00.png
PIDFILE=/tmp/quote-saver.pid
LOG=/mnt/us/quote-saver.log
SELF=$(readlink -f "$0" 2>/dev/null || echo "$0")

# ---------- daemon body ----------
# When this script is re-exec'd with the magic arg, it becomes the daemon.
if [ "$1" = "--daemon" ]; then
    # Detach fully: new session, no controlling tty, redirect all fds.
    echo $$ > "$PIDFILE"
    exec </dev/null >>"$LOG" 2>&1

    log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*"; }
    log "daemon started, pid=$$"

    # Clean PID file on exit.
    trap 'log "daemon exiting"; rm -f "$PIDFILE"; exit 0' INT TERM

    # Main event loop. -m = monitor (stream events forever).
    # We filter on goingToScreenSaver only; ignore everything else.
    lipc-wait-event -m com.lab126.powerd \
        goingToScreenSaver,outOfScreenSaver,readyToSuspend 2>>"$LOG" |
    while IFS= read -r EVENT; do
        case "$EVENT" in
            goingToScreenSaver*)
                log "event: $EVENT"
                if [ ! -f "$IMG" ]; then
                    log "image missing, skipping: $IMG"
                    continue
                fi
                # Let the framework finish its own screensaver draw first,
                # otherwise it overwrites us.
                sleep 1
                eips -f -g "$IMG" >>"$LOG" 2>&1
                log "painted $IMG"
                ;;
            *)
                # readyToSuspend / outOfScreenSaver / anything else: ignore.
                ;;
        esac
    done

    log "wait-event pipe closed, daemon dying"
    rm -f "$PIDFILE"
    exit 0
fi

# ---------- wrapper (tap entry point) ----------

# Already running?
if [ -f "$PIDFILE" ]; then
    OLDPID=$(cat "$PIDFILE" 2>/dev/null)
    if [ -n "$OLDPID" ] && kill -0 "$OLDPID" 2>/dev/null; then
        eips 0 25 "quote-saver already running (pid $OLDPID)"
        exit 0
    fi
    # Stale pidfile.
    rm -f "$PIDFILE"
fi

# Spawn daemon, fully detached. nohup + & + setsid (if available) for safety.
if command -v setsid >/dev/null 2>&1; then
    setsid /bin/sh "$SELF" --daemon </dev/null >>"$LOG" 2>&1 &
else
    nohup /bin/sh "$SELF" --daemon </dev/null >>"$LOG" 2>&1 &
fi

# Give it a moment to write its pidfile.
sleep 1

if [ -f "$PIDFILE" ]; then
    NEWPID=$(cat "$PIDFILE")
    eips 0 25 "quote-saver started (pid $NEWPID)"
else
    eips 0 25 "quote-saver: failed to start, see $LOG"
fi

exit 0
