from __future__ import annotations

import sys

import click

from mycli.packages.parseutils import is_destructive


class ConfirmBoolParamType(click.ParamType):
    name = "confirmation"

    def convert(self, value: bool | str, param: click.Parameter | None, ctx: click.Context | None) -> bool:
        if isinstance(value, bool):
            return bool(value)
        value = value.lower()
        if value in ("yes", "y"):
            return True
        if value in ("no", "n"):
            return False
        self.fail(f'{value} is not a valid boolean', param, ctx)

    def __repr__(self):
        return "BOOL"


BOOLEAN_TYPE = ConfirmBoolParamType()


def confirm_destructive_query(queries: str) -> bool | None:
    """Check if the query is destructive and prompts the user to confirm.

    Returns:
    * None if the query is non-destructive or we can't prompt the user.
    * True if the query is destructive and the user wants to proceed.
    * False if the query is destructive and the user doesn't want to proceed.

    """
    prompt_text = "You're about to run a destructive command.\nDo you want to proceed? (y/n)"
    if is_destructive(queries) and sys.stdin.isatty():
        return prompt(prompt_text, type=BOOLEAN_TYPE)
    else:
        return None


def confirm(*args, **kwargs) -> bool:
    """Prompt for confirmation (yes/no) and handle any abort exceptions."""
    try:
        return click.confirm(*args, **kwargs)
    except click.Abort:
        return False


def prompt(*args, **kwargs) -> bool:
    """Prompt the user for input and handle any abort exceptions."""
    try:
        return click.prompt(*args, **kwargs)
    except click.Abort:
        return False
