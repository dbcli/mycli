def make_dist():
    return default_python_distribution()

def make_exe(dist):
    policy = dist.make_python_packaging_policy()
    config = dist.make_python_interpreter_config()
    config.run_command = "from mycli.main import cli; cli()"
    exe = dist.to_python_executable(
        name="mycli",
        packaging_policy=policy,
        config=config,
    )

    return exe

def make_embedded_resources(exe):
    return exe.to_embedded_resources()

def make_install(exe):
    files = FileManifest()
    exe.add_python_resources(exe.pip_install(['.']))
    files.add_python_resource(".", exe)

    return files

register_target("dist", make_dist)
register_target("exe", make_exe, depends=["dist"])
register_target("resources", make_embedded_resources, depends=["exe"], default_build_script=True)
register_target("install", make_install, depends=["exe"], default=True)

resolve_targets()


PYOXIDIZER_VERSION = "0.10.3"
PYOXIDIZER_COMMIT = "UNKNOWN"
