"""Tests for linkbridge.midi_output."""

import pytest
from unittest.mock import MagicMock, patch

from linkbridge import midi_output


def test_list_outputs_returns_mido_output_names():
    with patch.object(midi_output.mido, "get_output_names", return_value=["A", "B"]):
        result = midi_output.list_outputs()
    assert isinstance(result, list)
    assert result == ["A", "B"]


def test_open_output_delegates_to_mido():
    fake_port = MagicMock(name="fake_port")
    with patch.object(midi_output.mido, "open_output", return_value=fake_port) as mock_open:
        result = midi_output.open_output("Circuit Tracks MIDI")
    mock_open.assert_called_once_with("Circuit Tracks MIDI")
    assert result is fake_port


def test_open_output_propagates_exceptions():
    with patch.object(midi_output.mido, "open_output", side_effect=IOError("nope")):
        with pytest.raises(IOError, match="nope"):
            midi_output.open_output("Ghost Device")
