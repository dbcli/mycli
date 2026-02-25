from prompt_toolkit.application import Application, run_in_terminal


def safe_invalidate_display(app: Application) -> None:
    """
    fzf can confuse the terminal/app when certain values are set in
    environment variable FZF_DEFAULT_OPTS.

    The same could happen after running other external programs.

    This function invalidates the prompt_toolkit display, causing a
    refresh of the prompt message and pending user input, without
    leading to exceptions at exit time, as the built-in
    app.invalidate() does.
    """

    def print_empty_string():
        app.print_text('')

    run_in_terminal(print_empty_string)
