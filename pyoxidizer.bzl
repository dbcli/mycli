def make_python_dist():
    return default_python_distribution()

def make_exe(dist):
    python_config = PythonInterpreterConfig(
        run_eval = "from mycli import main; main.cli()",
        sys_paths = ["$ORIGIN/lib", "$ORIGIN/app"],
    )

    exe = dist.to_python_executable(
        name = "mycli",
        config = python_config,
        extension_module_filter = "all",
        include_sources = True,
        include_resources = False,
        include_test = False,
    )
    exe.add_in_memory_python_resources(dist.pip_install([
        "-r",
        "./requirements/dist.txt",
    ]))

    return exe

def make_install(dist, exe):
    files = FileManifest()

    files.add_python_resource(".", exe)

    files.add_python_resources("app", dist.read_package_root(
        path = ".",
        packages = ["mycli"],
    ))

    return files

register_target("python_dist", make_python_dist)
register_target("exe", make_exe, depends = ["python_dist"])
register_target("install", make_install, depends = ["python_dist", "exe"], default = True)

resolve_targets()
