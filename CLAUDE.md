## Language use
- Everything public always in English.
- ALWAYS use simple and professional language in comments, docstrings, docs and PR descriptions. Try to avoid being poetic, aliterative or too verbose.
- Changelog entries must be short and to the point, a couple 80 len lines, not a paragrapah.
- README.md features descriptions, one or two paragraphs at most.
- PR descriptions, one or two paragrapahs at most.
- PR descriptions, comments and all that are PUBLIC, anybody could read them, so avoid using them to send messages to me in first person like writing "as you requested..." .
- Don't write stories related to our current testing campaigns in public places ("OPFOR had a problem with some ships so the player...").

## Questions
- When asked something about Escalation or DCS, don't guess, reply based on data files or code. If this doesn't work, search on the web. Try to keep your allucinations and guesses in check by using the code and data.

## Coding
- New features always go to a new branch and publish to an internal PR so I can review stuff easily. Bugfixes can go to an existing branch (the one that is being fixed) but also go to a PR. Never merge to master directly unless explicitly stated.
- Always work on a git worktreee. No need to do a new one for each bugfix or feature, you can keep one for the full session.
- Never reply to PR comments from other people yourself. If I tell you "handle this comment", it means to handle what the comments tell to fix or do, not to reply to the comment.
- Always check with black and mypy before pushing the PR.

## Troubleshooting and debugging
- Theories are Ok but they must be tested, typically by generating test missions to validate or falsify them.
