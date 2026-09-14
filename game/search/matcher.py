"""Scoring a typed query against a piece of text.

Written for the settings dialog, where the name a player remembers is rarely the one
on the label -- they remember "napalm", or "cadet", or that it was something about
parking -- and now shared with anything else that has to be found by typing part of
what it is called.

Every token has to match somewhere or the item is not a hit at all: the words are an
AND, not an OR. Where each one matches is what decides the order.

The matching is forgiving in one direction only. A token that is not a substring
anywhere still matches as a subsequence of the label ("frntline" finds "Maximum
frontline width"), but that is worth far less than a real hit, so a typo never
outranks the thing that was actually typed.
"""

from __future__ import annotations

import unicodedata

#: What a hit in each place is worth. A word the label starts with is what was meant;
#: a run of letters buried in an explanation probably is not.
SCORE_LABEL_WORD_START = 100
SCORE_LABEL = 60
SCORE_DETAIL = 20
SCORE_KEY = 15
SCORE_SUBSEQUENCE = 8

#: How far a subsequence may spread before it stops being a typo and starts being a
#: coincidence. "frntline" inside "frontline" spans nine letters for eight typed and
#: is clearly meant; "napalm" scattered across "Enable per-squadron pilot limits" is
#: not, and without a limit almost every long label matches almost every word.
SUBSEQUENCE_SLACK = 3

#: Below this a word is too short for the net to mean anything. "rank" is a tight
#: subsequence of "recovery tanker" -- the r of recovery and the ank of tanker -- and
#: it found four tanker settings that have nothing to do with ranks.
SUBSEQUENCE_MINIMUM = 6


def fold(text: str) -> str:
    """Lower case and without accents, so 'moral' finds 'Morale' either way."""
    stripped = unicodedata.normalize("NFD", text)
    return "".join(c for c in stripped if not unicodedata.combining(c)).lower()


def tokens_of(query: str) -> list[str]:
    """The words typed, folded. Empty when nothing was typed."""
    return [folded for word in query.split() if (folded := fold(word.strip()))]


def is_subsequence(needle: str, haystack: str) -> bool:
    """Every letter of needle, in order and close together. The typo net."""
    if len(needle) < SUBSEQUENCE_MINIMUM:
        return False
    limit = len(needle) + SUBSEQUENCE_SLACK
    for start in range(len(haystack)):
        if haystack[start] != needle[0]:
            continue
        found = 1
        for position in range(start + 1, min(len(haystack), start + limit)):
            if haystack[position] == needle[found]:
                found += 1
                if found == len(needle):
                    return True
    return False


def score_one(token: str, label: str, detail: str = "", key: str = "") -> int:
    """What one token is worth against one item, or 0 if it is not there.

    Everything passed in is already folded: this is the hot path, and folding the
    same label again for every keystroke is what made it hot.
    """
    if token in label:
        starts = any(word.startswith(token) for word in label.split())
        return SCORE_LABEL_WORD_START if starts else SCORE_LABEL
    if detail and token in detail:
        return SCORE_DETAIL
    # Only when it is plainly a key that is being typed. Otherwise an ordinary word
    # matches every item whose key happens to contain it: "rank" found all ten rank
    # name boxes through live_pilots_rank_good_short and the like, which is the
    # section's name showing through rather than a hit.
    if key and "_" in token and token in key:
        return SCORE_KEY
    if is_subsequence(token, label):
        return SCORE_SUBSEQUENCE
    return 0


def score_all(tokens: list[str], label: str, detail: str = "", key: str = "") -> int:
    """What every token together is worth, or 0 if any of them is missing.

    The words are an AND: "frontline width" should not answer with everything about
    frontlines and everything about widths.
    """
    total = 0
    for token in tokens:
        worth = score_one(token, label, detail, key)
        if not worth:
            return 0
        total += worth
    return total
