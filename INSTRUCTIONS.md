# Instructions for Claude — WOPR-9000

## Directory Structure

```
docs/                    ← gitignored entirely; all deployment-specific content lives here
  SYSTEM_PROMPT.md       ← Claude's persona and framing for this deployment
  FILES/                 ← appears in the FILE dropdown menu; human-browsable
  [other subdirs]/       ← background context for Claude; not in the FILE menu
```

## Which files belong in FILES/?

**Read the files.** A file belongs in `FILES/` if it contains explicit instructions for Claude — sections that tell Claude its role, how to behave, what to emphasize, or how to respond.

Common markers to look for:
- A section headed `NOTE TO CLAUDE` or similar
- Role definitions ("You are presenting this to...", "You are a messenger, not an advocate")
- Behavioral instructions ("Always make sure these land:", "Tone guidance:")
- Menu systems or response frameworks embedded in the document

Files that are **data sources** — primary documents, timelines, analyses, source transcripts — belong in subdirectories (e.g., `primary/`, `arguments/`, `sources/`) even if Claude uses them for context. The distinction is not "does Claude read this?" (Claude reads everything in `docs/`) but "does this file tell Claude *how to behave*?"

## The FILE dropdown

The FILE menu in the UI exposes `docs/FILES/` to the human user. These are the documents a user might want to read directly — typically the same documents that contain instructions for Claude, since those documents are usually also intended for a human reader.

Documents that are purely Claude context (analysis files, source transcripts, ranked arguments) do not need to be in `FILES/` and should stay in subdirectories.

## SYSTEM_PROMPT.md

`SYSTEM_PROMPT.md` at the root of `docs/` is excluded from the FILE menu automatically. It sets Claude's overall persona for the deployment. If a document in `FILES/` also contains Claude instructions, those instructions supplement (not replace) the system prompt.
