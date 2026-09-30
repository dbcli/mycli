from unittest.mock import Mock, call

import pytest

from mycli.packages import fzf as fzf_module
from mycli.packages.fzf import Fzf


@pytest.fixture
def prompt_process(monkeypatch: pytest.MonkeyPatch) -> Mock:
    process = Mock()
    process.communicate.return_value = ('selected\x00', None)
    monkeypatch.setattr(fzf_module, 'which', lambda executable: executable)
    monkeypatch.setattr(fzf_module.subprocess, 'Popen', Mock(return_value=process))
    return process


@pytest.mark.parametrize('executable', ['fzf', '/custom/bin/fzf'])
@pytest.mark.parametrize('available', [False, True])
def test_executable_availability(monkeypatch: pytest.MonkeyPatch, executable: str, available: bool) -> None:
    which = Mock(return_value='/resolved/fzf' if available else None)
    monkeypatch.setattr(fzf_module, 'which', which)

    wrapper = Fzf(executable)

    which.assert_called_once_with(executable)
    assert wrapper.executable == (executable if available else None)
    assert wrapper.is_available() is available


@pytest.mark.parametrize('options', [None, [], ['--no-height', "--preview=printf '%s' {}"]])
def test_prompt_passes_options_as_separate_arguments(
    prompt_process: Mock, monkeypatch: pytest.MonkeyPatch, options: list[str] | None
) -> None:
    popen = Mock(return_value=prompt_process)
    monkeypatch.setattr(fzf_module.subprocess, 'Popen', popen)
    original_options = None if options is None else list(options)

    Fzf('/custom/bin/fzf').prompt([], options=options)

    popen.assert_called_once_with(
        ['/custom/bin/fzf', '--read0', '--print0', *(options or [])],
        stdin=fzf_module.subprocess.PIPE,
        stdout=fzf_module.subprocess.PIPE,
        encoding='utf-8',
    )
    assert options == original_options


def test_prompt_falls_back_to_default_executable(prompt_process: Mock, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fzf_module, 'which', lambda executable: None)
    popen = Mock(return_value=prompt_process)
    monkeypatch.setattr(fzf_module.subprocess, 'Popen', popen)

    Fzf('/missing/fzf').prompt([])

    assert popen.call_args.args[0] == ['fzf', '--read0', '--print0']


def test_prompt_writes_nul_delimited_items_from_iterator(prompt_process: Mock) -> None:
    Fzf().prompt(iter(['SELECT 1\nFROM dual', 42, None, '']))

    assert prompt_process.stdin.write.call_args_list == [
        call('SELECT 1\nFROM dual\x00'),
        call('42\x00'),
        call('None\x00'),
        call('\x00'),
    ]
    prompt_process.communicate.assert_called_once_with()


@pytest.mark.parametrize(
    ('stdout', 'expected'),
    [
        ('', None),
        ('selected\x00', 'selected'),
        ('first\x00second\x00', 'first'),
        ('  SELECT 1\nFROM dual  \x00', '  SELECT 1\nFROM dual  '),
        ('selected', 'selected'),
        ('\x00', ''),
    ],
)
def test_prompt_returns_first_selection(prompt_process: Mock, stdout: str, expected: str | None) -> None:
    prompt_process.communicate.return_value = (stdout, None)

    assert Fzf().prompt([]) == expected


def test_prompt_recovers_selection_after_broken_pipe(prompt_process: Mock) -> None:
    prompt_process.stdin.write.side_effect = [None, BrokenPipeError('closed')]

    result = Fzf().prompt(['first', 'second', 'third'])

    assert prompt_process.stdin.write.call_args_list == [call('first\x00'), call('second\x00')]
    prompt_process.communicate.assert_called_once_with()
    assert result == 'selected'


def test_prompt_rejects_missing_input_stream(prompt_process: Mock) -> None:
    prompt_process.stdin = None

    with pytest.raises(AssertionError, match='Error creating fzf input stream'):
        Fzf().prompt(['item'])

    prompt_process.communicate.assert_not_called()


def test_prompt_propagates_write_errors(prompt_process: Mock) -> None:
    prompt_process.stdin.write.side_effect = OSError('write failed')

    with pytest.raises(OSError, match='write failed'):
        Fzf().prompt(['item'])


def test_prompt_propagates_communication_errors(prompt_process: Mock) -> None:
    prompt_process.communicate.side_effect = OSError('read failed')

    with pytest.raises(OSError, match='read failed'):
        Fzf().prompt([])


def test_prompt_propagates_process_start_errors(prompt_process: Mock, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fzf_module.subprocess, 'Popen', Mock(side_effect=FileNotFoundError('fzf missing')))

    with pytest.raises(FileNotFoundError, match='fzf missing'):
        Fzf().prompt([])
