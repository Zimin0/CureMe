"""Подбор под болезнь: нормализация, «стемминг», синонимы и порог совпадения."""

import pytest

from app.search import best_match, expand_query, normalize, phrase_coverage, stem, stems


def test_normalize_lowercases_and_drops_punctuation():
    assert normalize("Болит ГОЛОВА!!!").split() == ["болит", "голова"]
    assert normalize("Жёлчь") == "желчь"
    assert normalize(None) == ""


@pytest.mark.parametrize("word, expected", [
    ("головная", "головн"),  # отрезаем два последних символа
    ("голова", "голо"),
    ("нос", "нос"),     # короткие слова не режем
    ("жар", "жар"),
    ("сопли", "соп"),
])
def test_stem(word, expected):
    assert stem(word) == expected


def test_stems_drop_stop_words_and_single_letters():
    assert stems("что делать, если у меня болит голова") == [stem("если"), stem("болит"), stem("голова")]
    assert stems("я") == []


def test_phrase_coverage():
    text = stems("головная боль, зубная боль")
    assert phrase_coverage(stems("головная боль"), text) == 1.0
    assert phrase_coverage(stems("головная температура"), text) == 0.5
    assert phrase_coverage([], text) == 0.0
    assert phrase_coverage(stems("боль"), []) == 0.0


def test_expand_query_adds_synonyms_with_lower_weight():
    phrases = dict(expand_query("болит голова"))
    assert phrases["болит голова"] == 1.0
    assert phrases["мигрень"] == 0.8 and phrases["головная боль"] == 0.8


def test_expand_query_word_forms():
    """«понос» и «поносом» должны находить одну группу синонимов."""
    assert "диарея" in dict(expand_query("понос"))
    assert "диарея" in dict(expand_query("поносом"))
    assert "жар" in dict(expand_query("Температуры"))


def test_expand_query_unknown_condition_has_only_itself():
    assert expand_query("пяточная шпора") == [("пяточная шпора", 1.0)]


@pytest.mark.parametrize("query, text, found", [
    ("мигрень", "мигрень, головная боль", True),
    ("болит голова", "головная боль", True),        # через синонимы
    ("головная боль", "зубная боль", True),         # половина фразы из двух слов — считается
    ("мигрень", "насморк", False),
    ("кашель", "", False),
])
def test_best_match(query, text, found):
    score, which = best_match(expand_query(query), text)
    assert (score > 0) is found
    assert (which is not None) is found


def test_single_word_needs_full_match():
    # у однословной фразы нет «половинчатых» совпадений
    assert best_match([("насморк", 1.0)], "заложенность носа") == (0.0, None)


def test_exact_query_beats_synonym():
    score_exact, _ = best_match(expand_query("мигрень"), "мигрень")
    score_syn, _ = best_match(expand_query("мигрень"), "головная боль")
    assert score_exact > score_syn
