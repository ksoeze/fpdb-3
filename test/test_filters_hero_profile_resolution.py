"""Selecting a "[Profile]" entry in the Heroes filter reported on nobody.

Filters.getHeroes() returns {} for a multiroom profile on purpose -- the
docstring points at get_selected_hero_profile() instead -- but every report
inlined the same loop over getHeroes() alone:

    for site in sites:
        _hname = heroes.get(site, "")
        if not _hname:
            continue        # always taken, so playerids stayed empty

so the graph, session, opponents and tourney views all rendered empty for a
profile while working fine for a plain "<hero> on <site>" selection. The loop
now lives once, in Filters.resolve_hero_player_ids, and understands both.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from fpdb_3_legacy.Filters import Filters

SITE = "iPoker"


class _HeroList:
    """Stand-in for the Heroes QComboBox: only its current item matters."""

    def __init__(self, data, text: str = "") -> None:
        self._data = data
        self._text = text

    def currentData(self):
        return self._data

    def currentText(self) -> str:
        return self._text


class _Db:
    """Player lookups, backed by a name -> (playerId, siteId) table."""

    def __init__(self, players: dict[str, tuple[int, int | None]], hero_flagged: list[int] | None = None) -> None:
        self.players = players
        self.hero_flagged = hero_flagged or []

    def get_player_id(self, _conf, _site, name):
        entry = self.players.get(name)
        return entry[0] if entry else None

    def get_hero_player_ids(self, _site=None, profile=None):  # noqa: ARG002
        return list(self.hero_flagged)

    def get_player_name_by_id(self, pid):
        for name, (player_id, _site_id) in self.players.items():
            if player_id == pid:
                return name
        return None

    def get_player_site_id(self, pid):
        for _name, (player_id, site_id) in self.players.items():
            if player_id == pid:
                return site_id
        return None


def _filters(hero_list: _HeroList, db: _Db, profiles: dict | None = None) -> Filters:
    # Filters is a QWidget; the resolution logic needs none of that machinery,
    # so bypass __init__ rather than standing up a window per test.
    flt = Filters.__new__(Filters)
    flt.heroList = hero_list
    flt.db = db
    flt.conf = SimpleNamespace(get_hero_profiles=lambda: profiles or {})
    return flt


def _profile(links: list[tuple[str, str]]):
    by_site: dict[str, list[str]] = {}
    for site, alias in links:
        by_site.setdefault(site, []).append(alias)
    return SimpleNamespace(name="Me", aliases_by_site=lambda: by_site)


def test_profile_selection_resolves_every_alias() -> None:
    # Regression: this returned ([], [], []) and the reports drew nothing.
    db = _Db({"happpypeppi": (8, 14), "LastNick": (23, 14)})
    flt = _filters(
        _HeroList(("profile", "Me")),
        db,
        {"Me": _profile([(SITE, "happpypeppi"), (SITE, "LastNick")])},
    )

    playerids, sitenos, names = flt.resolve_hero_player_ids([SITE], {SITE: 14})

    assert playerids == [8, 23]
    assert sitenos == [14, 14]
    assert names == [f"happpypeppi on {SITE}", f"LastNick on {SITE}"]


def test_profile_skips_aliases_that_are_not_in_the_database() -> None:
    # A profile names its aliases explicitly, so an alias that was never
    # imported must not widen the report to every hero-flagged player.
    db = _Db({"happpypeppi": (8, 14)}, hero_flagged=[8, 99])
    flt = _filters(
        _HeroList(("profile", "Me")),
        db,
        {"Me": _profile([(SITE, "happpypeppi"), (SITE, "not_imported_yet")])},
    )

    playerids, _sitenos, _names = flt.resolve_hero_player_ids([SITE], {SITE: 14})

    assert playerids == [8]


def test_the_same_player_reached_twice_is_listed_once() -> None:
    db = _Db({"happpypeppi": (8, 14)})
    flt = _filters(
        _HeroList(("profile", "Me")),
        db,
        {"Me": _profile([(SITE, "happpypeppi"), (SITE, "happpypeppi")])},
    )

    playerids, sitenos, names = flt.resolve_hero_player_ids([SITE], {SITE: 14})

    assert playerids == [8]
    assert len(sitenos) == len(names) == 1


def test_profile_site_name_matches_case_insensitively() -> None:
    # The profile stores whatever spelling the config used.
    db = _Db({"happpypeppi": (8, 14)})
    flt = _filters(
        _HeroList(("profile", "Me")),
        db,
        {"Me": _profile([("ipoker", "happpypeppi")])},
    )

    playerids, _sitenos, _names = flt.resolve_hero_player_ids([SITE], {SITE: 14})

    assert playerids == [8]


def test_a_single_hero_selection_still_resolves() -> None:
    db = _Db({"happpypeppi": (8, 14)})
    flt = _filters(_HeroList(("site_alias", SITE, "happpypeppi")), db)

    playerids, sitenos, names = flt.resolve_hero_player_ids([SITE], {SITE: 14})

    assert playerids == [8]
    assert sitenos == [14]
    assert names == [f"happpypeppi on {SITE}"]


def test_a_single_hero_falls_back_to_the_sites_hero_flagged_players() -> None:
    # Unchanged behaviour: an unresolved single hero widens to hero=1 players.
    db = _Db({"someone_else": (42, 14)}, hero_flagged=[42])
    flt = _filters(_HeroList(("site_alias", SITE, "renamed_account")), db)

    playerids, _sitenos, _names = flt.resolve_hero_player_ids([SITE], {SITE: 14})

    assert playerids == [42]


def test_unknown_player_site_falls_back_to_the_filters_site_id() -> None:
    db = _Db({"happpypeppi": (8, None)})
    flt = _filters(_HeroList(("site_alias", SITE, "happpypeppi")), db)

    _playerids, sitenos, _names = flt.resolve_hero_player_ids([SITE], {SITE: 14})

    assert sitenos == [14]


@pytest.mark.parametrize("selection", [("profile", "Me"), ("site_alias", SITE, "happpypeppi")])
def test_a_site_with_no_matching_alias_contributes_nothing(selection) -> None:
    db = _Db({"happpypeppi": (8, 14)})
    flt = _filters(_HeroList(selection), db, {"Me": _profile([(SITE, "happpypeppi")])})

    playerids, sitenos, names = flt.resolve_hero_player_ids([], {})

    assert (playerids, sitenos, names) == ([], [], [])
