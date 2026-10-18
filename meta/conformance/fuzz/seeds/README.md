# Recorded fuzz seeds

Recorded hook payloads the differential fuzz run (`meta/conformance/fuzz.py`, C111) mutates
alongside the payloads of the hook scenarios. One file per payload, named
`<script>--<label>.json` (`<script>` is the hook that receives it, e.g.
`delegation-nudge--pretooluse-read-3f2a1c09bd.json`), holding exactly one JSON object: the stdin
document. A recorded seed runs on the `base` fixture, natively attached and synced.

A recorded payload goes here **only scrubbed of private content**: no consumer or session text
(prompts, messages, tool output, file contents), session and tool-use ids replaced by
neutral ones, and every path rewritten to hang from `{{root}}` (the fixture project) or
`{{tmp}}` (the run tempdir). A payload that cannot be scrubbed without losing what made it
interesting stays out.

## How to record

The payloads are real ones from our own work on akmon, recorded with
`meta/conformance/fuzz_record.py` (standard library only) in three steps.

1. **Capture.** Wire `fuzz_record.py tee` in your *untracked* `.claude/settings.local.json`, on
   the events and matchers whose payloads you want, with a capture directory **outside the
   repository** — raw captures are private material and are never committed (`tee` records
   nothing into a directory inside the repository). `tee` writes each stdin to
   `<DIR>/<script>--<n>.json` and then runs the command after `--` on the same bytes, its stdout,
   stderr and exit code passed through unchanged; a failed capture is skipped silently and never
   changes what the hook does. Claude Code runs the hooks of every settings file, so the hook
   wired in `.claude/settings.json` still runs on its own: wrap `true` to capture only, as below,
   and name the hook with `--script`.

   ```json
   {
     "hooks": {
       "PreToolUse": [
         {
           "matcher": "Bash|Edit|Write|MultiEdit|Task|Agent|Read|Grep|Glob",
           "hooks": [
             {
               "type": "command",
               "command": "python3 \"$CLAUDE_PROJECT_DIR/meta/conformance/fuzz_record.py\" tee --out \"$HOME/akmon-fuzz-raw\" --script delegation-nudge -- true"
             }
           ]
         }
       ]
     }
   }
   ```

   A hook no other settings file wires is wrapped whole instead:
   `... tee --out "$HOME/akmon-fuzz-raw" -- python3 "$CLAUDE_PROJECT_DIR/hooks/<script>.py"`.
   Remove the wiring when you have enough captures.

2. **Scrub.** `python3 meta/conformance/fuzz_record.py scrub --raw "$HOME/akmon-fuzz-raw"
   --project-root "$PWD"` is a dry run: one line per capture — the seed it would write, a capture
   with the shape of one already kept (one seed per script and key/type shape, the seeds already
   here included), or a capture it skips and why (not one JSON object, or a path under the home
   directory outside the project inside a longer string, such as a Bash command). Paths under the
   project become `{{root}}`, under the tempdir `{{tmp}}`, any other whole-value path under the
   home directory `/home/user/elsewhere`; every `*_id` string becomes a fixed neutral one; the
   free-text members (`prompt`, `message`, `tool_response`, `content`, `old_string`,
   `new_string`, `new_source`, `description`, `last_assistant_message`, `custom_instructions`,
   `summary`, `reason`, `text`, `pattern`, `query`) keep their keys and types with every string
   in them replaced by `scrubbed`. The routing fields (`hook_event_name`, `tool_name`,
   `subagent_type`, `model`, `cwd`, a Bash `command`) stay, paths rewritten. `--apply` writes the
   seeds here.

3. **Review.** The owner reads every new seed before it is committed: a Bash command or another
   kept string can still carry text worth removing, and a seed that is not worth its run time is
   deleted. Only reviewed seeds are committed; the raw captures stay outside the repository.
