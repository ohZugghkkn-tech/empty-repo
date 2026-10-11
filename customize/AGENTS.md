# Agent Instructions

## Workspace Guidance

This file holds project-specific conventions for this workspace. Durable facts about
the user belong in `USER.md`, personality and reasoning style in `SOUL.md`, long-term
memory in `memory/MEMORY.md`.

## Tool-First Policy

The agent in this workspace is configured to **execute**, not to describe. These rules
override any instinct to answer from memory.

### Arithmetic and exact computation

Any question involving numbers that must be *correct* goes through `exec` with Python:

```bash
python3 -c "print(2481 + 837382)"
```

This applies to arithmetic, percentages, unit conversions, date math, statistics,
string manipulation, and anything where "approximately" is not good enough.
An answer computed in the head is a guess wearing a number's clothing.

### Facts that change

Anything about versions, prices, releases, news, or "the latest" is fetched, not
recalled. Use `web_search`, then `web_fetch` on the best source.

### Files and code

- `read_file` before editing anything. No blind writes.
- `apply_patch` for multi-file or structural edits; `edit_file` for one exact replacement.
- After editing, read back the changed region to confirm it applied.
- Run the code you wrote. An untested answer is not an answer.

### Counting

Do not count by inspection. Use `rg -c`, `wc -l`, `find | wc -l`, or a Python one-liner.

## Verification Discipline

1. **Restate the goal** in one line before a long task. If the request is ambiguous in a
   way that changes the output, ask — otherwise pick the obvious reading and proceed.
2. **Plan briefly**, then execute. No narration between steps unless asked.
3. **Check the result** against the request: right file, right format, right number.
4. **Report the outcome**, including failures. If something did not work, say so first,
   not buried at the end.
5. **Never claim success** for a step whose output was not observed.

## Failure Handling

- Tool error → read the message, adjust, retry once. Still failing → report the exact error.
- Missing credentials or capabilities → name the missing piece. Do not silently substitute.
- Uncertain about a fact → say "unverified" rather than asserting it.

## Environment Notes

- Put scratch files inside the workspace, not in system directories.
- Prefer non-destructive commands. Before deleting or overwriting, confirm the target.
- Use `cron` for time-based reminders — never just write a reminder into memory, because
  that will not notify anyone.

## Scheduled Reminders

- Check available skills before scheduling.
- Use the built-in `cron` tool to create, list, or remove jobs; do not call the CLI via `exec`.
- Use `cron` for a specific time or interval, including recurring tasks like "every day at 8".
- The tool captures the current chat automatically; instructions need only describe the task.

**Do NOT just write reminders to MEMORY.md** — that will not trigger a notification.

## Heartbeat Tasks

`HEARTBEAT.md` is checked periodically by the protected heartbeat cron job registered when
`gateway.heartbeat.enabled` is true. Do not create a duplicate heartbeat job unless the
built-in one was disabled deliberately.

- `apply_patch` for normal task-list edits, especially multi-line changes.
- `edit_file` only for small exact replacements copied from the current file.
- `write_file` for first creation or intentional full rewrites.

Heartbeat is for flexible background checks that notify only on actionable change. It
does not guarantee a time. "Send me a report every day at 8am" needs `cron`, not heartbeat.
