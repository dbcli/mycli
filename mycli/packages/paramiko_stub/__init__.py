"""A module to import instead of paramiko when it is not available (to avoid
checking for paramiko all over the place).

When paramiko is first envoked, it simply shuts down mycli, telling
user they either have to install paramiko or should not use SSH
features.

"""


class Paramiko:
    def __getattr__(self, name):
        import sys
        from textwrap import dedent

        print(
            dedent("""
            To enable certain SSH features you need to install paramiko and sshtunnel:

               pip install paramiko sshtunnel

            It is required for the following configuration options:
                --list-ssh-config
                --ssh-config-host
                --ssh-host
        """)
        )
        sys.exit(1)


paramiko = Paramiko()
