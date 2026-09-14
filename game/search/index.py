"""Everything nameable in a campaign, in one list, searchable by typing.

A campaign of moderate size has seven hundred-odd things worth finding by name: two
hundred and forty settings, three hundred pilots, a hundred and twenty-five
objectives, and the squadrons, flights and bases between them. A large one has
several thousand.

Which is why the text is folded once, here, rather than on every keystroke. Folding
normalises and rebuilds a string, and the settings search did it to every label, every
explanation and every key each time a letter was typed; at two hundred and forty
settings that was already four milliseconds, and it grows with the campaign.

The search then runs in two passes. The first asks only whether every word appears
somewhere in the entry at all -- one C-level substring test, which throws out almost
everything -- and scores the survivors. The second is the typo net, and only runs when
the first found little: a query that answered well does not need "frntline" to also
find "frontline".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Optional
from weakref import ReferenceType, ref

from game.search.matcher import (
    SCORE_SUBSEQUENCE,
    is_subsequence,
    score_one,
    tokens_of,
)

#: What a word found among an entry's keywords is worth. Between a label hit and a
#: hit in the explanation: a site named MINK holding a Patriot launcher is a good
#: answer to "patriot", and a better one than a setting whose detail mentions it.
SCORE_KEYWORD = 40

#: How many hits the first pass has to find before the typo net is not worth running.
#: A query that answered is not a typo.
ENOUGH_WITHOUT_THE_NET = 8


@dataclass(frozen=True)
class Follow:
    """What to do when an entry is chosen.

    A pair of strings rather than a callable: the index is built in ``game`` and
    cannot open a dialog. The user interface resolves the pair.
    """

    kind: str
    key: str


@dataclass(frozen=True)
class Entry:
    """One findable thing: what it is called, where it is, and how to reach it."""

    label: str
    detail: str
    follow: Follow
    #: Words that should find it without being shown -- the unit types inside an
    #: objective, the aircraft a squadron flies, the page a setting lives on.
    keywords: str = ""
    #: The identifier it is stored under, searched only when a key is plainly what
    #: was typed.
    key: str = ""
    #: Shown in the row, greyed: a limitation worth admitting at the point of use.
    note: str = ""

    folded_label: str = field(init=False, repr=False, compare=False)
    folded_detail: str = field(init=False, repr=False, compare=False)
    folded_keywords: str = field(init=False, repr=False, compare=False)
    folded_key: str = field(init=False, repr=False, compare=False)
    haystack: str = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        from game.search.matcher import fold

        label, detail = fold(self.label), fold(self.detail)
        keywords, key = fold(self.keywords), fold(self.key)
        object.__setattr__(self, "folded_label", label)
        object.__setattr__(self, "folded_detail", detail)
        object.__setattr__(self, "folded_keywords", keywords)
        object.__setattr__(self, "folded_key", key)
        object.__setattr__(self, "haystack", f"{label} {detail} {keywords} {key}")

    def score(self, tokens: list[str]) -> int:
        """What the query is worth against this entry, or 0 if a word is missing.

        The best of the places it appears, not the first. "Harrier" is in a
        squadron's detail line and in its keywords, and in the keywords of every
        pilot in it: taking the first match made the squadron worth twenty and each
        of its fifteen pilots worth forty, so the squadron came last.
        """
        total = 0
        for token in tokens:
            worth = max(
                score_one(
                    token, self.folded_label, self.folded_detail, self.folded_key
                ),
                SCORE_KEYWORD if token in self.folded_keywords else 0,
            )
            if not worth:
                return 0
            total += worth
        return total

    def score_by_typo(self, tokens: list[str]) -> int:
        """What it is worth if every word is a near miss of the label."""
        for token in tokens:
            if not is_subsequence(token, self.folded_label):
                return 0
        return SCORE_SUBSEQUENCE * len(tokens)


#: Which kind wins when two entries are worth the same. A command palette is for
#: commands first; a squadron is a better answer to "harrier" than one of its
#: pilots, and there are four hundred pilots to get past.
KIND_PREFERENCE = {
    "action": 7,
    "base": 6,
    "squadron": 5,
    "flight": 4,
    "objective": 3,
    "setting": 2,
    "pilot": 1,
}


@dataclass(frozen=True)
class Hit:
    entry: Entry
    score: int

    @property
    def order(self) -> tuple[int, int, int, str]:
        """Best first: worth, then kind, then the shorter label, then alphabetical.

        A short label matching beats a long one saying the same thing further in.
        """
        return (
            -self.score,
            -KIND_PREFERENCE.get(self.entry.follow.kind, 0),
            len(self.entry.label),
            self.entry.label,
        )


class Index:
    """A flat list of entries, folded once and searched many times."""

    def __init__(self, entries: Iterable[Entry] = ()) -> None:
        self.entries: list[Entry] = list(entries)

    def __len__(self) -> int:
        return len(self.entries)

    def search(self, query: str, limit: int = 40) -> list[Hit]:
        """Every entry that matches all of the words typed, best first."""
        tokens = tokens_of(query)
        if not tokens:
            return []

        hits: list[Hit] = []
        missed: list[Entry] = []
        for entry in self.entries:
            haystack = entry.haystack
            if all(token in haystack for token in tokens):
                score = entry.score(tokens)
                if score:
                    hits.append(Hit(entry, score))
                    continue
            missed.append(entry)

        if len(hits) < ENOUGH_WITHOUT_THE_NET:
            for entry in missed:
                score = entry.score_by_typo(tokens)
                if score:
                    hits.append(Hit(entry, score))

        hits.sort(key=lambda hit: hit.order)
        return hits[:limit]


class GameIndex:
    """The index for one campaign, rebuilt when the campaign moves on.

    Held rather than rebuilt per keystroke, and thrown away rather than patched: a
    turn changes the flights, the pilots and half the objectives at once, and
    following each of those would be more bookkeeping than the rebuild costs.
    """

    def __init__(self) -> None:
        self._index: Optional[Index] = None
        # A weak reference, and compared with `is`. The campaign's address is not its
        # identity: a campaign that has been freed leaves the address behind for the
        # next one, and an index keyed on it would answer about the old one. A strong
        # reference would keep a whole dead campaign alive to avoid that.
        self._built_from: Optional[ReferenceType[Any]] = None
        self._built_on_turn: Optional[int] = None

    def of(self, game: Optional[Any]) -> Index:
        built_from = self._built_from() if self._built_from is not None else None
        turn = getattr(game, "turn", None)
        if self._index is None or built_from is not game or turn != self._built_on_turn:
            from game.search.providers import entries_for

            self._index = Index(entries_for(game))
            self._built_from = ref(game) if game is not None else None
            self._built_on_turn = turn
        return self._index

    def forget(self) -> None:
        self._index = None
        self._built_from = None
        self._built_on_turn = None
