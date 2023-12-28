import os
import sys

from importlib.util import spec_from_file_location, module_from_spec
from importlib import reload

from SCons.Variables import *

import os
import sys
from collections import OrderedDict
from collections.abc import Mapping
from typing import Iterator
from os.path import normpath, basename
import itertools

class AbsFile(SCons.Node.FS.File):
    def __init__(self, name, directory, fs):
         super().__init__(name, directory, fs)
    
    #override __str__ to return abs path
    def __str__(self):
        return self.get_abspath()

def CreateAbsFile(env, name, directory = None, fs = None):
    if type(directory) == str:
        directory = env.Dir(directory, fs)
    return AbsFile(name, directory, fs)

def get_cmdline_bool(option, default):
    """We use `ARGUMENTS.get()` to check if options were manually overridden on the command line,
    and SCons' _text2bool helper to convert them to booleans, otherwise they're handled as strings.
    """
    from SCons.Script import ARGUMENTS
    from SCons.Variables.BoolVariable import _text2bool

    cmdline_val = ARGUMENTS.get(option)
    if cmdline_val is not None:
        return _text2bool(cmdline_val)
    else:
        return default

def generate_cpp_hint_file(filename):
    if os.path.isfile(filename):
        # Don't overwrite an existing hint file since the user may have customized it.
        pass
    else:
        try:
            with open(filename, "w") as fd:
                fd.write("#define GDCLASS(m_class, m_inherits)\n")
        except OSError:
            print("Could not write cpp.hint file.")


def glob_recursive(pattern, node="."):
    from SCons import Node
    from SCons.Script import Glob

    results = []
    for f in Glob(str(node) + "/*", source=True):
        if type(f) is Node.FS.Dir:
            results += glob_recursive(pattern, f)
    results += Glob(str(node) + "/" + pattern, source=True)
    return results


def find_visual_c_batch_file(env):
    from SCons.Tool.MSCommon.vc import get_default_version, get_host_target, find_batch_file, find_vc_pdir

    # Syntax changed in SCons 4.4.0.
    from SCons import __version__ as scons_raw_version

    scons_ver = env._get_major_minor_revision(scons_raw_version)

    msvc_version = get_default_version(env)

    if scons_ver >= (4, 4, 0):
        (host_platform, target_platform, _) = get_host_target(env, msvc_version)
    else:
        (host_platform, target_platform, _) = get_host_target(env)

    if scons_ver < (4, 6, 0):
        return find_batch_file(env, msvc_version, host_platform, target_platform)[0]

    # Scons 4.6.0+ removed passing env, so we need to get the product_dir ourselves first,
    # then pass that as the last param instead of env as the first param as before.
    # We should investigate if we can avoid relying on SCons internals here.
    product_dir = find_vc_pdir(env, msvc_version)
    return find_batch_file(msvc_version, host_platform, target_platform, product_dir)[0]


def add_to_vs_project(env, sources):
    for x in sources:

        if type(x) == type(""):
            x = env.File(x)
        fname = x.get_abspath()
        pieces = fname.split(".")
        if len(pieces) > 0:
            basename = pieces[0]
            basename = basename.replace("\\\\", "/")
            if os.path.isfile(basename + ".h"):
                env.vs_incs += [basename + ".h"]
            elif os.path.isfile(basename + ".hpp"):
                env.vs_incs += [basename + ".hpp"]
            if os.path.isfile(basename + ".c"):
                env.vs_srcs += [basename + ".c"]
            elif os.path.isfile(basename + ".cpp"):
                env.vs_srcs += [basename + ".cpp"]


# generate vs project for extension - modified from godot engine sconstruct
def generate_vs_project(original_env, original_args, project_path = "", project_sources = [], header_directories = [], binary_root = "bin", binary_prefix = "" ,binary_ext = "dll"):
    env = original_env.Clone()
    if not os.path.isabs(binary_root):
        binary_root = os.path.join(os.path.dirname(project_path), binary_root)
    if binary_prefix == "":
        binary_prefix = os.path.basename(project_path)

    
    batch_file = find_visual_c_batch_file(env)
    filtered_args = original_args.copy()
    # Ignore the "vsproj" option to not regenerate the VS project on every build
    filtered_args.pop("vsproj", None)
    # The "platform" option is ignored because only the Windows platform is currently supported for VS projects
    filtered_args.pop("platform", None)
    # The "target" option is ignored due to the way how targets configuration is performed for VS projects (there is a separate project configuration for each target)
    filtered_args.pop("target", None)
    # The "progress" option is ignored as the current compilation progress indication doesn't work in VS
    filtered_args.pop("progress", None)

    project_targets = []

    #TODO: Maybe add this as a mode to mono/non-mono? For now just add options if originally built with dev_build - also need to unhard code from run file
    cli_base_args = ["dev_build=yes"] if env["dev_build"] else []
    if batch_file:

        class ModuleConfigs(Mapping):
            # This version information (Win32, x64, Debug, Release) seems to be
            # required for Visual Studio to understand that it needs to generate an NMAKE
            # project. Do not modify without knowing what you are doing.
            PLATFORMS = ["Win32", "x64"]
            PLATFORM_IDS = ["x86_32", "x86_64"]
            CONFIGURATIONS = ["editor", "template_release", "template_debug"]
            DEV_SUFFIX = ".dev" if "dev_build" in env and env["dev_build"] else ""

            @staticmethod
            def for_every_variant(value):
                return [value for _ in range(len(ModuleConfigs.CONFIGURATIONS) * len(ModuleConfigs.PLATFORMS))]

            def __init__(self):
                shared_targets_array = []
                self.names = []
                self.arg_dict = {
                    "variant": [],
                    "runfile": shared_targets_array,
                    "buildtarget": shared_targets_array,
                    "cpppaths": [],
                    "cppdefines": [],
                    "cmdargs": [],
                }
                self.add_mode()  # default

            def add_mode(
                self,
                name: str = "",
                includes: str = "",
                cli_args: list[str] = [],
                defines=None,
            ):
                if defines is None:
                    defines = []
                if "CPPDEFINES" not in env:
                    env["CPPDEFINES"] = []
                self.names.append(name)
                self.arg_dict["variant"] += [
                    f'{config}{f"_[{name}]" if name else ""}|{platform}'
                    for config in ModuleConfigs.CONFIGURATIONS
                    for platform in ModuleConfigs.PLATFORMS
                ]
                dev_suffix = "dev." if env["dev_build"] else ""
                #TODO: Do I need to add double handling to binary like godot.ext does? Maybe not?
                self.arg_dict["runfile"] += [
                    # This pattern must match windows binary file that is being produced for configuration
                    #f"{binary_root}\\{binary_prefix}.windows.{config}.{dev_suffix}{plat_id}.{binary_ext}"
                    os.path.basename(project_path)
                    for config in ModuleConfigs.CONFIGURATIONS
                    for plat_id in ModuleConfigs.PLATFORM_IDS
                ]
                self.arg_dict["cpppaths"] += ModuleConfigs.for_every_variant(env["CPPPATH"] + [includes])
                self.arg_dict["cppdefines"] += ModuleConfigs.for_every_variant(list(env["CPPDEFINES"]) + defines)
                #self.arg_dict["cmdargs"] += ModuleConfigs.for_every_variant(cli_args)
                self.arg_dict["cmdargs"] += [
                    " ".join(cli_base_args + cli_args + [f"target={config}", f'platform=windows', f'arch={platform}']) #hard-coded platform to windows since vs is only on windows
                    for config in ModuleConfigs.CONFIGURATIONS
                    for platform in ModuleConfigs.PLATFORM_IDS
                ]

            def build_commandline(self, commands):
                configuration_getter = (
                    "$(Configuration"
                    + "".join([f'.Replace("{name}", "")' for name in self.names[1:]])
                    + '.Replace("_[]", "")'
                    + ")"
                )

                common_build_prefix = [
                    'cmd /V /C set "plat=$(PlatformTarget)"',
                    '(if "$(PlatformTarget)"=="x64" (set "plat=x86_amd64"))',
                    'call "' + batch_file + '" !plat!',
                ]

                # Windows allows us to have spaces in paths, so we need
                # to double quote off the directory. However, the path ends
                # in a backslash, so we need to remove this, lest it escape the
                # last double quote off, confusing MSBuild
                common_build_postfix = [
                    "--directory=\"$(ProjectDir.TrimEnd('\\'))\"",
                    "platform=windows",
                    f"target={configuration_getter}",
                    "progress=no",
                ]

                for arg, value in filtered_args.items():
                    common_build_postfix.append(f"{arg}={value}")

                result = " ^& ".join(common_build_prefix + [" ".join([commands] + common_build_postfix)])
                return result

            # Mappings interface definitions

            def __iter__(self) -> Iterator[str]:
                for x in self.arg_dict:
                    yield x

            def __len__(self) -> int:
                return len(self.names)

            def __getitem__(self, k: str):
                return self.arg_dict[k]

        add_to_vs_project(env, project_sources)

        for header_dir in header_directories:
            add_to_vs_project(env, glob_recursive("/**/*.h", header_dir))

        module_configs = ModuleConfigs()

        if env.get("module_mono_enabled"):
            mono_defines = [("GD_MONO_HOT_RELOAD",)] if env.editor_build else []
            module_configs.add_mode(
                "mono",
                cli_args=["module_mono_enabled=yes"],
                defines=mono_defines,
            )

        env["MSVSBUILDCOM"] = module_configs.build_commandline("scons")
        env["MSVSREBUILDCOM"] = module_configs.build_commandline("scons vsproj=yes")
        env["MSVSCLEANCOM"] = module_configs.build_commandline("scons --clean")
        if not env.get("MSVS"):
            env["MSVS"]["PROJECTSUFFIX"] = ".vcxproj"
            env["MSVS"]["SOLUTIONSUFFIX"] = ".sln"
        

        project_targets += [env.MSVSProject(
            target=[project_path + env.get("MSVSPROJECTSUFFIX", ".vcxproj")],
            incs=env.vs_incs,
            srcs=env.vs_srcs,
            auto_build_solution=env.get("auto_build_solution", False),
            **module_configs,
        )]
    else:
        print("Could not locate Visual Studio batch file to set up the build environment. Not generating VS project.")
    return project_targets

def generate_vs_solution(env, original_args, solution_name, projects_to_include):
    batch_file = find_visual_c_batch_file(env)
    filtered_args = original_args.copy()
    # Ignore the "vsproj" option to not regenerate the VS project on every build
    filtered_args.pop("vsproj", None)
    # The "platform" option is ignored because only the Windows platform is currently supported for VS projects
    filtered_args.pop("platform", None)
    # The "target" option is ignored due to the way how targets configuration is performed for VS projects (there is a separate project configuration for each target)
    filtered_args.pop("target", None)
    # The "progress" option is ignored as the current compilation progress indication doesn't work in VS
    filtered_args.pop("progress", None)

    solutions_generated = []
    if batch_file:
        class ModuleConfigs():
            PLATFORMS = ["Win32", "x64"]
            CONFIGURATIONS = ["editor", "template_release", "template_debug"]
        
        if not env.get("MSVS"):
            env["MSVS"]["PROJECTSUFFIX"] = ".vcxproj"
            env["MSVS"]["SOLUTIONSUFFIX"] = ".sln"
        

        env.Tool("msvs")
        
        module_configs = ModuleConfigs()
        if env.get("module_mono_enabled"):
            for i in range(len(module_configs.CONFIGURATIONS)-1,-1,-1):
                module_configs.CONFIGURATIONS.insert(i+1, module_configs.CONFIGURATIONS[i] + "_[mono]")


        solutions_generated += [env.MSVSSolution(
            target=["#" + solution_name + env.get("MSVSSOLUTIONSUFFIX", ".sln")],
            projects = projects_to_include,
            variant = ["{0}|{1}".format(variants[0], variants[1]) for variants in itertools.product(module_configs.CONFIGURATIONS, module_configs.PLATFORMS)] #todo figure out variant and how  module config fits in
        )]
        pass
    else:
        print("Could not locate Visual Studio batch file to set up the build environment. Not generating VS project.")
    return solutions_generated

def add_shared_library(env, name, sources, **args):
    library = env.SharedLibrary(name, sources, **args)
    env.NoCache(library)
    return library


def add_library(env, name, sources, **args):
    library = env.Library(name, sources, **args)
    env.NoCache(library)
    return library


def add_program(env, name, sources, **args):
    program = env.Program(name, sources, **args)
    env.NoCache(program)
    return program

#find directory by name in current directory or parent directories
def find_dir_by_name(search_path, name):
    def get_child_directories(parent_directory):
        return [entry for entry in os.listdir(parent_directory) if os.path.isdir(os.path.join(parent_directory, entry))]

    curr = search_path

    while os.path.isdir(curr) and not any([dir == name for dir in get_child_directories(curr)]):
        curr = os.path.dirname(curr)

    curr = os.path.join(curr, name)
    return curr if os.path.isdir(curr) else ""

# find godot cpp gdextension bindings and add them to build
def get_godot_engine_source_root(search_path, godot_source_name=""):
    return find_dir_by_name(search_path, godot_source_name or "Godot")


# find godot cpp gdextension bindings and add them to build
def get_cpp_extension_root(search_path, extension_root_name=""):
    return find_dir_by_name(search_path, extension_root_name or "godot-cpp")

def get_extenstion_source_directories(root_directory):
    extension_source_directories = []
    for root, dirs, files in os.walk(root_directory):
        if "SCSub" in files:
            extension_source_directories += [ root]
    return extension_source_directories
    

def get_options(env, customs, args):
    opts = Variables(customs, args)
    opts.Add(BoolVariable("vsproj", "Generate a Visual Studio solution", False))
    opts.Add(BoolVariable("force_rebuild_vsproj", "Force rebuild of VS Project and Solutions even if they haven't changed", False))
    opts.Add("solution_name", "Name of the Visual Studio solution", os.path.basename(os.getcwd()))
    opts.Add("cpp_extension_root", "Directory of cpp extension", get_cpp_extension_root(os.getcwd()))
    opts.Add("godot_source_root", "Directory of godot source code", get_godot_engine_source_root(os.getcwd()))
    opts.Add(BoolVariable("module_mono_enabled", "Set to true to enable mono module", False))
    return opts

def write_gd_extension_text(env, f, extension_name):
    entry_symbol = env.get("ext_entry_symbol", "library_init")
    compatibility_minimum = env.get("ext_compatibility_minimum", "4.1")
    
    extension_base = f"bin/{extension_name}"
    ext_platforms = env.get("ext_platforms", ["Win64"])
 
    def writeline(s):
        f.write(s + "\n")

    writeline('[configuration]')
    writeline('')
    writeline(f'entry_symbol = "{entry_symbol}"')
    writeline(f'compatibility_minimum = "{compatibility_minimum}"')
    writeline('')
    writeline('[libraries]')
    writeline('')

    dev_suffix = ".dev" if env["dev_build"] else ""

    configs = ["editor", "template_debug", "template_release"]
    def write_variants(s):
        for c in configs:
            writeline(s.format(extension_base=extension_base, config = c, dev_suffix = dev_suffix))

    if("macos" in ext_platforms):
        write_variants('macos.{config} = "{extension_base}.macos.{config}{dev_suffix}.framework"')
    if("Win32" in ext_platforms):
        write_variants('windows.{config}.x86_32 = "{extension_base}.windows.{config}{dev_suffix}.x86_32.dll"')
    if("Win64" in ext_platforms or "Windows" in ext_platforms):
        write_variants('windows.{config}.x86_64 = "{extension_base}.windows.{config}{dev_suffix}.x86_64.dll"')
    if("linux" in ext_platforms):
        write_variants('linux.{config}.x86_64 = "{extension_base}.linux.{config}{dev_suffix}.x86_64.so"')
        write_variants('linux.{config}.arm64 = "{extension_base}.linux.{config}{dev_suffix}.arm64.so"')
        write_variants('linux.{config}.rv64 = "{extension_base}.linux.{config}{dev_suffix}.rv64.so"')
    if("android" in ext_platforms):
        write_variants('android.{config}.x86_64 = "{extension_base}.android.{config}{dev_suffix}.x86_64.so"')
        write_variants('android.{config}.arm64 = "{extension_base}.android.{config}{dev_suffix}.arm64.so"')

def register_builders(env):
     env['BUILDERS']['write_gdextension_file'] = SCons.Builder.Builder(action=write_gdextension_action, suffix = ".gdextension", emitter = emitter_remove_source)
     env['BUILDERS']['write_gdignore_file'] = SCons.Builder.Builder(action=write_gdignore_action, emitter = emitter_gdignore)

def write_gdextension_action(target, source, env):
    ext_name = os.path.splitext(os.path.basename(str(target[0])))[0]
    with open(target[0].get_abspath(), "w") as f:
        write_gd_extension_text(env, f, ext_name)

def write_gdignore_action(target, source, env):
    #write empty file named .gdignore
    with open(target[0].get_abspath(), "w") as f:
        pass

def emitter_remove_source(target, source, env):
    source = []
    return (target, source)

def emitter_gdignore(target, source, env):
    source = []
    #target is list of directories to write .gdignore files to
    for i in range(len(target)):
        target[i] = os.path.join(target[i].get_abspath(), ".gdignore")
    return (target, source)


def export_customs(Import, Export, ARGUMENTS):
    # Import customs and profiles
    try:
        Import("customs")
    except:
        customs = []
    customs += ["custom.py"]

    profile = ARGUMENTS.get("profile", "")
    if profile:
        if os.path.isfile(profile):
            customs.append(profile)
        elif os.path.isfile(profile + ".py"):
            customs.append(profile + ".py")

    customs = list(map(os.path.abspath, customs))
    Export("customs")
    return customs