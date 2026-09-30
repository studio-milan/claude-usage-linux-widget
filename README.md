# claude-usage-linux-widget
A status bar widget showing Claude usage and remaining resoucres for week / session

Claude Usage Indicator - Rev00

What it shows

The status bar shows a double ring icon plus a label, for example S11% 2:53 · W31% 2d02h.
·	S is the 5-hour session: percentage used and countdown to reset (hours:minutes).
·	W is the 7-day week: percentage used and countdown to reset (days and hours).
·	Outer ring is the session,  inner ring is the week.
·	Colors compare usage with elapsed time: green means go heavy (more than 10 points under pace), amber means on pace, red means save (more than 10 points over pace, or above 95%).
·	A trailing ! means the last refresh failed and the numbers are stale.

Clicking the icon opens the detail menu: reset times, percentage of time elapsed, projected usage at reset, weekly budget per remaining day, last update, "Refresh now", and a link to the claude.ai usage page. The same details are set as hover text, which appears only if the panel host supports indicator tooltips (see Known limits).
Notifications

One desktop notification per window, per event:
·	Session at 80% or more.
·	Week projected to exceed 100% before reset (with more than 12 hours left): save.
·	Last 24 hours of the week with less than 85% used: use it or lose it (your Friday morning).

Thresholds are constants at the top of the script (SESSION_ALERT, PACE_MARGIN, WEEK_LAST_CALL_HOURS, WEEK_LAST_CALL_BELOW, POLL_SECONDS).



Install (requires all files to be in the same folder)

chmod +x install-Rev00.sh

 ./install-Rev00.sh

 
/.local/bin/, registers autostart at login, runs a one-shot check, and starts the indicator.
