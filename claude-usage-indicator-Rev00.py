#!/usr/bin/env python3
"""
Claude Usage Indicator - Rev00

Ubuntu status bar indicator for Claude subscription usage:
  - 5-hour session window  (outer ring)
  - 7-day week window      (inner ring)

Data source: the undocumented endpoint used by Claude Code's /usage screen,
authenticated with the OAuth (Open Authorization) token that Claude Code keeps
in ~/.claude/.credentials.json. The token is sent only to api.anthropic.com.

Usage:
  claude-usage-indicator-Rev00.py          run the status bar indicator
  claude-usage-indicator-Rev00.py --once   print a text summary and exit
"""

import hashlib
import json
import math
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ---------------------------------------------------------------- settings --
REV = "Rev00"
APP_ID = "claude-usage-indicator"
CREDS_FILE = Path.home() / ".claude" / ".credentials.json"
CACHE_DIR = Path.home() / ".cache" / APP_ID
ICON_DIR = CACHE_DIR / "icons"
NOTIFIED_FILE = CACHE_DIR / "notified.json"
ENDPOINT = "https://api.anthropic.com/api/oauth/usage"
USAGE_PAGE = "https://claude.ai/settings/usage"

POLL_SECONDS = 180          # how often to ask Anthropic for fresh numbers
TICK_SECONDS = 30           # how often countdowns are redrawn locally
PACE_MARGIN = 10.0          # +/- percentage points around "on pace"
SESSION_ALERT = 80.0        # notify when session usage reaches this
WEEK_LAST_CALL_HOURS = 24   # "use it or lose it" window before weekly reset
WEEK_LAST_CALL_BELOW = 85.0 # ...only if weekly usage is below this

SESSION_LEN = timedelta(hours=5)
WEEK_LEN = timedelta(days=7)

COLORS = {"green": "#43a047", "amber": "#ffb300", "red": "#e53935", "grey": "#9e9e9e"}
TRACK = "#6b6b6b"
ADVICE = {"green": "go heavy", "amber": "on pace", "red": "save", "grey": "idle"}


# ------------------------------------------------------------------ model --
class Window:
    """One rolling usage window (session or week)."""

    def __init__(self, name, length, raw):
        raw = raw or {}
        self.name = name
        self.length = length
        self.used = float(raw.get("utilization") or 0.0)
        ra = raw.get("resets_at")
        self.resets_at = datetime.fromisoformat(ra.replace("Z", "+00:00")) if ra else None

    def remaining(self, now):
        if not self.resets_at:
            return None
        return max(self.resets_at - now, timedelta(0))

    def elapsed_pct(self, now):
        rem = self.remaining(now)
        if rem is None:
            return None
        return max(0.0, min(100.0, 100.0 * (1 - rem / self.length)))

    def projected(self, now):
        """Usage at reset if the current average pace continues."""
        e = self.elapsed_pct(now)
        if e is None or e < 5:
            return None
        return self.used * 100.0 / e

    def state(self, now):
        if self.resets_at is None:
            return "grey" if self.used == 0 else "amber"
        if self.used >= 95:
            return "red"
        diff = self.used - self.elapsed_pct(now)
        if diff > PACE_MARGIN:
            return "red"
        if diff < -PACE_MARGIN:
            return "green"
        return "amber"

    def key(self):
        """Stable identifier of this window instance (for one-shot alerts)."""
        if not self.resets_at:
            return f"{self.name}:none"
        t = self.resets_at.replace(second=0, microsecond=0)
        t = t - timedelta(minutes=t.minute % 15)
        return f"{self.name}:{t.isoformat()}"


def fmt_countdown(td):
    if td is None:
        return "--"
    mins = int(td.total_seconds() // 60)
    d, rem = divmod(mins, 1440)
    h, m = divmod(rem, 60)
    return f"{d}d{h:02d}h" if d else f"{h}:{m:02d}"


def fmt_reset(dt, now):
    if dt is None:
        return "not started"
    loc = dt.astimezone()
    if loc.date() == now.astimezone().date():
        return loc.strftime("%H:%M")
    return loc.strftime("%a %d %b %H:%M")


def panel_label(s, w, now):
    return (f"S{s.used:.0f}% {fmt_countdown(s.remaining(now))}"
            f" · W{w.used:.0f}% {fmt_countdown(w.remaining(now))}")


def describe(s, w, now):
    """Detail lines shared by the menu, the tooltip and --once."""
    lines = []
    for win in (s, w):
        title = "Session (5h)" if win is s else "Week (7d)"
        lines.append(f"{title}: {win.used:.0f}% used, resets {fmt_reset(win.resets_at, now)}"
                     f" (in {fmt_countdown(win.remaining(now))})")
        e = win.elapsed_pct(now)
        p = win.projected(now)
        pace = f"{e:.0f}% of time elapsed" if e is not None else "window not started"
        proj = f", projected {p:.0f}% at reset" if p is not None else ""
        lines.append(f"   pace: {pace}{proj} -> {ADVICE[win.state(now)].upper()}")
    rem = w.remaining(now)
    if rem is not None and rem.total_seconds() > 0:
        days = max(rem.total_seconds() / 86400, 1 / 24)
        lines.append(f"Weekly budget: {max(0, 100 - w.used):.0f}% left, "
                     f"about {max(0, 100 - w.used) / days:.0f}% per remaining day")
    return lines


# ------------------------------------------------------------------- data --
class UsageError(Exception):
    pass


def claude_version():
    try:
        out = subprocess.run(["claude", "--version"], capture_output=True,
                             text=True, timeout=10).stdout.strip()
        return out.split()[0] if out else "2.1.0"
    except Exception:
        return "2.1.0"


def read_token():
    try:
        data = json.loads(CREDS_FILE.read_text())
    except FileNotFoundError:
        raise UsageError("No Claude Code credentials: run 'claude' and log in")
    except Exception as e:
        raise UsageError(f"Cannot read credentials: {e}")
    tok = (data.get("claudeAiOauth") or {}).get("accessToken")
    if not tok:
        raise UsageError("No OAuth token found: run 'claude' and log in")
    return tok


def fetch_usage(version):
    req = urllib.request.Request(ENDPOINT, headers={
        "Authorization": f"Bearer {read_token()}",
        "anthropic-beta": "oauth-2025-04-20",
        "User-Agent": f"claude-code/{version}",
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        if e.code == 401:
            raise UsageError("Token expired: open Claude Code once to refresh it")
        if e.code == 429:
            raise UsageError("Rate limited by Anthropic, will retry")
        raise UsageError(f"HTTP error {e.code}")
    except urllib.error.URLError as e:
        raise UsageError(f"Network error: {e.reason}")


# ------------------------------------------------------------------- icon --
def ring_svg(s, w, now):
    def ring(r, pct, color, width):
        c = 2 * math.pi * r
        filled = c * max(0.0, min(pct, 100.0)) / 100.0
        return (f'<circle cx="11" cy="11" r="{r}" fill="none" stroke="{TRACK}" '
                f'stroke-width="{width}" opacity="0.55"/>'
                f'<circle cx="11" cy="11" r="{r}" fill="none" stroke="{color}" '
                f'stroke-width="{width}" stroke-dasharray="{filled:.2f} {c:.2f}" '
                f'transform="rotate(-90 11 11)"/>')
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 22 22">'
            + ring(9.3, s.used, COLORS[s.state(now)], 3.2)
            + ring(4.6, w.used, COLORS[w.state(now)], 3.2)
            + '</svg>')


def write_icon(svg):
    ICON_DIR.mkdir(parents=True, exist_ok=True)
    name = "cui-" + hashlib.md5(svg.encode()).hexdigest()[:10]
    path = ICON_DIR / f"{name}.svg"
    if not path.exists():
        path.write_text(svg)
        # keep the icon folder small
        icons = sorted(ICON_DIR.glob("cui-*.svg"), key=lambda p: p.stat().st_mtime)
        for old in icons[:-20]:
            old.unlink(missing_ok=True)
    return name, path


# ---------------------------------------------------------- notifications --
def load_notified():
    try:
        return set(json.loads(NOTIFIED_FILE.read_text()))
    except Exception:
        return set()


def save_notified(keys):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    NOTIFIED_FILE.write_text(json.dumps(sorted(keys)[-50:]))


def notify(title, body, icon_path=None):
    cmd = ["notify-send", "-a", "Claude Usage", title, body]
    if icon_path:
        cmd[1:1] = ["-i", str(icon_path)]
    try:
        subprocess.Popen(cmd)
    except FileNotFoundError:
        pass


def check_alerts(s, w, now, notified, icon_path):
    changed = False

    def once(key, title, body):
        nonlocal changed
        if key not in notified:
            notified.add(key)
            changed = True
            notify(title, body, icon_path)

    if s.used >= SESSION_ALERT:
        once(s.key() + ":high", f"Claude session at {s.used:.0f}%",
             f"Resets at {fmt_reset(s.resets_at, now)} (in {fmt_countdown(s.remaining(now))}).")

    p = w.projected(now)
    wrem = w.remaining(now)
    if p is not None and p >= 100 and wrem and wrem > timedelta(hours=12):
        once(w.key() + ":overrun", "Claude week: slow down",
             f"At this pace you reach {p:.0f}% before the reset "
             f"({fmt_reset(w.resets_at, now)}). Save resources.")

    if (wrem is not None and timedelta(0) < wrem <= timedelta(hours=WEEK_LAST_CALL_HOURS)
            and w.used < WEEK_LAST_CALL_BELOW):
        once(w.key() + ":lastcall", "Claude week: use it or lose it",
             f"{100 - w.used:.0f}% of the week still unused, resets "
             f"{fmt_reset(w.resets_at, now)} (in {fmt_countdown(wrem)}). Go heavy.")

    if changed:
        save_notified(notified)


# -------------------------------------------------------------------- CLI --
def run_once():
    try:
        data = fetch_usage(claude_version())
    except UsageError as e:
        print(f"Error: {e}")
        return 1
    now = datetime.now(timezone.utc)
    s, w = Window("session", SESSION_LEN, data.get("five_hour")), Window("week", WEEK_LEN, data.get("seven_day"))
    print(panel_label(s, w, now))
    print("\n".join(describe(s, w, now)))
    return 0


# -------------------------------------------------------------------- GUI --
def run_indicator():
    import gi
    gi.require_version("Gtk", "3.0")
    try:
        gi.require_version("AyatanaAppIndicator3", "0.1")
        from gi.repository import AyatanaAppIndicator3 as AppInd
    except (ValueError, ImportError):
        gi.require_version("AppIndicator3", "0.1")
        from gi.repository import AppIndicator3 as AppInd
    from gi.repository import GLib, Gtk

    class Indicator:
        def __init__(self):
            self.version = claude_version()
            self.data = None
            self.error = None
            self.last_ok = None
            self.busy = False
            self.notified = load_notified()

            ICON_DIR.mkdir(parents=True, exist_ok=True)
            self.ind = AppInd.Indicator.new(APP_ID, "", AppInd.IndicatorCategory.APPLICATION_STATUS)
            self.ind.set_icon_theme_path(str(ICON_DIR))
            self.ind.set_status(AppInd.IndicatorStatus.ACTIVE)

            self.menu = Gtk.Menu()
            self.info_items = []
            for _ in range(5):
                it = Gtk.MenuItem(label="")
                it.set_sensitive(False)
                self.menu.append(it)
                self.info_items.append(it)
            self.menu.append(Gtk.SeparatorMenuItem())
            self.status_item = Gtk.MenuItem(label="Loading...")
            self.status_item.set_sensitive(False)
            self.menu.append(self.status_item)
            for label, cb in (("Refresh now", lambda *_: self.refresh()),
                              ("Open claude.ai usage page", self.open_page),
                              (f"Quit ({REV})", lambda *_: Gtk.main_quit())):
                it = Gtk.MenuItem(label=label)
                it.connect("activate", cb)
                self.menu.append(it)
            self.menu.show_all()
            self.ind.set_menu(self.menu)

            self.render()
            self.refresh()
            GLib.timeout_add_seconds(POLL_SECONDS, self.refresh)
            GLib.timeout_add_seconds(TICK_SECONDS, self.tick)

        def open_page(self, *_):
            subprocess.Popen(["xdg-open", USAGE_PAGE])

        def tick(self):
            self.render()
            return True

        def refresh(self):
            if not self.busy:
                self.busy = True
                threading.Thread(target=self._fetch, daemon=True).start()
            return True

        def _fetch(self):
            try:
                data, err = fetch_usage(self.version), None
            except UsageError as e:
                data, err = None, str(e)
            except Exception as e:
                data, err = None, f"Unexpected error: {e}"
            GLib.idle_add(self._on_result, data, err)

        def _on_result(self, data, err):
            self.busy = False
            if data is not None:
                self.data, self.error, self.last_ok = data, None, datetime.now()
            else:
                self.error = err
            self.render(alerts=data is not None)
            return False

        def render(self, alerts=False):
            now = datetime.now(timezone.utc)
            if self.data is None:
                svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="22" height="22">'
                       f'<circle cx="11" cy="11" r="8" fill="none" stroke="{COLORS["grey"]}" stroke-width="3"/></svg>')
                name, _ = write_icon(svg)
                self.ind.set_icon_full(name, "Claude usage")
                self.ind.set_label("Claude ?", "Claude ?")
                self.status_item.set_label(self.error or "Loading...")
                self.ind.set_title(self.error or "Claude usage: loading")
                return

            s = Window("session", SESSION_LEN, self.data.get("five_hour"))
            w = Window("week", WEEK_LEN, self.data.get("seven_day"))
            name, path = write_icon(ring_svg(s, w, now))
            self.ind.set_icon_full(name, "Claude usage")
            stale = " !" if self.error else ""
            self.ind.set_label(panel_label(s, w, now) + stale, "S100% 4:59 · W100% 6d23h !")

            lines = describe(s, w, now)
            for item, text in zip(self.info_items, lines + [""] * 5):
                item.set_label(text)
                item.set_visible(bool(text))
            updated = self.last_ok.strftime("%H:%M") if self.last_ok else "--"
            self.status_item.set_label(
                f"Updated {updated}" + (f" - {self.error}" if self.error else ""))
            # Hover text: shown only if the panel host supports indicator tooltips
            self.ind.set_title("\n".join(lines))

            if alerts:
                check_alerts(s, w, now, self.notified, path)

    Indicator()
    Gtk.main()


if __name__ == "__main__":
    if "--once" in sys.argv:
        sys.exit(run_once())
    run_indicator()
