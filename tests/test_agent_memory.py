"""core/agent/memory.py: the notes the agent keeps between sessions."""

import pytest

from max_cli.common.exceptions import ValidationError
from max_cli.core.agent import memory as memory_module
from max_cli.core.agent.memory import AgentMemory, memory_file


def test_notes_live_in_the_max_folder_and_start_empty():
    assert memory_file().parent.name == ".max_cli"
    assert AgentMemory().notes() == []
    assert AgentMemory().prompt_lines() == ""


def test_the_same_fact_twice_keeps_one_note():
    memory = AgentMemory()

    first = memory.remember("Music lives in  D:/Music")
    again = memory.remember("music lives in D:/Music")

    assert again == first
    assert [note.text for note in memory.notes()] == ["Music lives in D:/Music"]


@pytest.mark.parametrize("text", ["", "   ", "x" * (memory_module.MAX_NOTE_CHARS + 1)])
def test_empty_and_long_notes_are_refused(text):
    with pytest.raises(ValidationError):
        AgentMemory().remember(text)


def test_the_oldest_notes_go_past_the_limit(monkeypatch):
    monkeypatch.setattr(memory_module, "MAX_NOTES", 3)
    memory = AgentMemory()

    for number in range(5):
        memory.remember(f"fact {number}")

    assert [note.text for note in memory.notes()] == ["fact 2", "fact 3", "fact 4"]


def test_forget_and_clear():
    memory = AgentMemory()
    kept = memory.remember("keep me")
    gone = memory.remember("drop me")

    assert memory.forget(gone.id) == gone
    assert memory.forget("no-such-id") is None
    assert memory.notes() == [kept]
    assert memory.clear() == 1
    assert memory.notes() == []


def test_a_broken_file_reads_as_no_notes():
    memory_file().parent.mkdir(parents=True, exist_ok=True)
    memory_file().write_text("{not json", encoding="utf-8")

    assert AgentMemory().notes() == []
    AgentMemory().remember("works again")
    assert [note.text for note in AgentMemory().notes()] == ["works again"]
