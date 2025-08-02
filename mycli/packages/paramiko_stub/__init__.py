"""A module to import instead of paramiko when it is not available (to avoid
checking for paramiko all over the place).

When paramiko is first invoked, this simply shuts down mycli, telling the
user they either have to install paramiko or should not use SSH features.

"""


class Paramiko:
    def __getattr__(self, name: str) -> None:
        import sys
        from textwrap import dedent

        print(
            dedent("""
            To enable certain SSH features you need to install ssh extras:

                pip install 'mycli[ssh]'

            or

                pip install paramiko sshtunnel

            This is required for the following command-line arguments:

                --list-ssh-config
                --ssh-config-host
                --ssh-host
            """),
            file=sys.stderr,
        )
        sys.exit(1)


paramiko = Paramiko()
