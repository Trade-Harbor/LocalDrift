"""Reddit bot package.

Outbound integration with r/Wilmington. Generates monthly markdown
roundups of LocalDrift events and (later) posts + stickies them via
PRAW.

This phase (Phase D of the launch plan) is pure dry-run: formatter +
fetcher + preview. No PRAW dependency yet, no cron, no live posts.
The point is to have something concrete to show the r/Wilmington mods
so they can pick a format with the community via a vote thread.
"""
