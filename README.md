# Claude Usage Indicator - Rev04
# Credits - Ing. Rocco Abram - rocco.abram@3ngi.com - https://github.com/studio-milan/

## What it shows

The status bar shows a double ring icon plus a label, for example `11% 2:53 · W 31% 2d02h`.

- **The first value** is the 5-hour session: percentage used and countdown to reset (hours:minutes).
- **W** is the 7-day week: percentage used and countdown to reset (days and hours).
- **Outer ring** is the session, **inner ring** is the week.
- **Colors** compare usage with the share of time elapsed in the window: green means go heavy (usage at most 10 points above elapsed time), amber means ease off (10 to 20 points above), red means save (more than 20 points above, or above 95%).
- A trailing `!` means the numbers are not fresh, followed by the reason: `! wait` (rate limited, retries with growing pauses), `! login`, `! offline` (no network, retries every 30 seconds), `! error`. A bare `!` right after a restart means the last saved reading is shown while fresh data arrives.
- Without any reading, the label shows the reason alone: `Claude: login`, `Claude: wait`, `Claude: offline`, `Claude: error`.

Clicking the icon opens the detail menu: reset times, percentage of time elapsed, projected usage at reset, weekly budget per remaining day, last update, "Refresh now", and a link to the claude.ai usage page. The same details are set as hover text, which appears only if the panel host supports indicator tooltips (see Known limits).

## Notifications

One desktop notification per window, per event:

- Session at 80% or more.
- Week projected to exceed 100% before reset (with more than 12 hours left): save.
- Last 24 hours of the week with less than 85% used: use it or lose it (your Friday morning).

Thresholds are constants at the top of the script (`SESSION_ALERT`, `PACE_MARGIN`, `WEEK_LAST_CALL_HOURS`, `WEEK_LAST_CALL_BELOW`, `POLL_SECONDS`).

## Install

```bash
chmod +x install-Rev04.sh
./install-Rev04.sh
```

The installer adds the dependencies, copies the script to `~/.local/bin/`, registers autostart at login, runs a one-shot check, and starts the indicator.

Terminal check at any time:

```bash
~/.local/bin/claude-usage-indicator-Rev04.py --once
```

## Uninstall

```bash
pkill -f "claude-usage-indicator-.*\.py"
rm -f ~/.local/bin/claude-usage-indicator-Rev04.py ~/.config/autostart/claude-usage-indicator*.desktop
rm -rf ~/.cache/claude-usage-indicator
```

## Known limits

- **Undocumented endpoint.** The data comes from `api.anthropic.com/api/oauth/usage`, the same source as Claude Code's /usage screen. Anthropic may change it without notice.
- **Token lifetime.** The Claude Code login token lasts about 8 hours. When it expires, the widget first tries to renew it itself. If Anthropic refuses (as observed in practice), it falls back to Claude Code: it runs `claude -p` once with the smallest model (Haiku) in an empty folder, and Claude Code renews and saves the token itself. This uses a negligible amount of usage and starts a 5-hour session window at that moment (typically at the first boot of the day). The fallback runs at most once every 2 hours.
- **Log.** Starts, token renewals and errors are written to `~/.cache/claude-usage-indicator/log.txt`.
- **Hover.** Ubuntu's AppIndicator host may not display hover text. Click the icon for the details. A native GNOME Shell extension with real hover support is possible in a future revision.
- **Polling.** Numbers refresh every 3 minutes (or on "Refresh now"). Countdowns update every 30 seconds.
