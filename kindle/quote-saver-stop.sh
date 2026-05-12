#!/bin/sh
# quote-saver-stop.sh — stops the quote-saver daemon.
# Drop into /mnt/us/documents/ alongside quote-saver.sh.

PIDFILE=/tmp/quote-saver.pid
LOG=/mnt/us/quote-saver.log

if [ ! -f "$PIDFILE" ]; then
    eips 0 25 "quote-saver not running (no pidfile)"
    exit 0
fi

PID=$(cat "$PIDFILE" 2>/dev/null)

if [ -z "$PID" ] || ! kill -0 "$PID" 2>/dev/null; then
    eips 0 25 "quote-saver not running (stale pidfile)"
    rm -f "$PIDFILE"
    exit 0
fi

# Polite first.
kill "$PID" 2>/dev/null
# Give it up to 3s to clean up.
i=0
while [ $i -lt 3 ] && kill -0 "$PID" 2>/dev/null; do
    sleep 1
    i=$((i + 1))
done

# Force if still alive.
if kill -0 "$PID" 2>/dev/null; then
    kill -9 "$PID" 2>/dev/null
fi

# lipc-wait-event is a separate child; clean it up too.
# (It dies on its own when the pipe closes, but belt-and-braces.)
pkill -f "lipc-wait-event -m com.lab126.powerd" 2>/dev/null

rm -f "$PIDFILE"
echo "$(date '+%Y-%m-%d %H:%M:%S') stopped pid $PID" >>"$LOG"
eips 0 25 "quote-saver stopped (pid $PID)"
exit 0
