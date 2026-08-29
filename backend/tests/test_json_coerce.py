"""
Tests for src.api.json_coerce — asyncpg JSONB string coercion helpers.
"""

from src.api.json_coerce import as_dict, as_list


class TestAsList:
    def test_passthrough_when_already_list(self):
        assert as_list(["a", "b"]) == ["a", "b"]

    def test_passthrough_empty_list(self):
        assert as_list([]) == []

    def test_decodes_valid_json_string(self):
        assert as_list('["Margin compression", "Rate risk"]') == [
            "Margin compression",
            "Rate risk",
        ]

    def test_invalid_json_string_returns_empty_list(self):
        assert as_list("not valid json") == []

    def test_empty_string_returns_empty_list(self):
        assert as_list("") == []

    def test_none_returns_empty_list(self):
        assert as_list(None) == []

    def test_json_string_encoding_a_dict_returns_empty_list(self):
        assert as_list('{"a": 1}') == []

    def test_json_string_encoding_a_number_returns_empty_list(self):
        assert as_list("5") == []

    def test_json_string_encoding_null_returns_empty_list(self):
        assert as_list("null") == []


class TestAsDict:
    def test_passthrough_when_already_dict(self):
        assert as_dict({"ticker": "AAPL"}) == {"ticker": "AAPL"}

    def test_passthrough_empty_dict(self):
        assert as_dict({}) == {}

    def test_decodes_valid_json_string(self):
        assert as_dict('{"ticker": "AAPL", "volume": 100}') == {
            "ticker": "AAPL",
            "volume": 100,
        }

    def test_invalid_json_string_returns_empty_dict(self):
        assert as_dict("not valid json") == {}

    def test_empty_string_returns_empty_dict(self):
        assert as_dict("") == {}

    def test_none_returns_empty_dict(self):
        assert as_dict(None) == {}

    def test_json_string_encoding_a_list_returns_empty_dict(self):
        assert as_dict("[1, 2, 3]") == {}

    def test_json_string_encoding_a_number_returns_empty_dict(self):
        assert as_dict("5") == {}

    def test_json_string_encoding_null_returns_empty_dict(self):
        assert as_dict("null") == {}
