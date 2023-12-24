#!/usr/bin/env python
import os
import SConstructCommon

customs = SConstructCommon.export_customs(Import, Export, ARGUMENTS)

# Create the environment
env = Environment(tools=['default'])
original_args = ARGUMENTS
opts = SConstructCommon.get_options(env, customs, original_args)
opts.Update(env)
Export("env")

#TODO: More graceful handling of cpp extension missing. Not sure if possible to be more graceful
# build the cpp extension. Pop off arguments before doing so to avoid warning
for key in opts.keys():
    if key in ARGUMENTS:
        del ARGUMENTS[key]
env = SConscript(os.path.join(env["cpp_extension_root"], "SConstruct"))

# add godot-cpp as first project if it extists
projects_to_build = []
if env["vsproj"]:
    godot_cpp_sources = []
    def add_sources(dir, extension):
        abs_path = os.path.join(env["cpp_extension_root"], dir)
        for f in os.listdir(abs_path):
            if f.endswith("." + extension):
                godot_cpp_sources.append(abs_path + "/" + f)
    add_sources("src", "cpp")
    add_sources("src/classes", "cpp")
    add_sources("src/core", "cpp")
    add_sources("src/variant", "cpp")
    projects_to_build.append([os.path.join(env["cpp_extension_root"], "godot-cpp"), godot_cpp_sources, [env["cpp_extension_root"]] ])  


# find all extensions under project root and build them as sub projects - generate vs projects if desired
extension_source_directories = SConstructCommon.get_extenstion_source_directories(os.getcwd())
default_args = []
env.glob_recursive = SConstructCommon.glob_recursive
SConstructCommon.register_builders(env)
for directory in extension_source_directories:
    ext_env = env.Clone()
    ext_env.additional_targets = []
    ext_env = SConscript(os.path.join(directory, "SCSub"), exports="ext_env")
    extension_sources = []
    for f in ext_env.extension_sources:
        f = str(f)
        f = f if os.path.isabs(f) else os.path.join(os.getcwd(), f)
        extension_sources.append(f)

    default_args += ext_env.additional_targets;
    # build extension binaries
    ext_name = os.path.basename(directory)
    if env["platform"] == "macos":
        library = ext_env.SharedLibrary(
            f"bin/{ext_name}.{ext_env['platform']}.{ext_env['target']}.framework/{ext_name}.{ext_env['platform']}.{ext_env['target']}",
            source= extension_sources,
        )
    else:
        library = ext_env.SharedLibrary(
            f"bin/{ext_name}{ext_env['suffix']}{ext_env['SHLIBSUFFIX']}",
            source= extension_sources,
        )
    default_args += [library]

    # add the project as a project to build
    if ext_env["vsproj"]:
        header_directories = [directory, 
                            #env["cpp_extension_root"],
                            #env["godot_source_root"],
                            ]
        projects_to_build += [[os.path.join(directory, ext_name), extension_sources, header_directories]]


## create a vsproj with the source files
if env["vsproj"]:    
    if os.name != "nt":
        print("Error: The `vsproj` option is only usable on Windows with Visual Studio.")
        Exit(255)
    # TODO: Need to test with multiple extensions. It's possible that multiple extensions could fail to generate vsproject correctly
    env["CPPPATH"] = [Dir(path) for path in env["CPPPATH"]]

    env["auto_build_solution"] = False
    projects = []

    for project in projects_to_build:
        env.vs_incs = []
        env.vs_srcs = []
        projects += SConstructCommon.generate_vs_project(env, original_args, *project)
        default_args += projects
    #TODO: Add this hint file to the projects that are generated
    #SConstructCommon.generate_cpp_hint_file("cpp.hint")


    #TODO: Build a project with extra configuration

    #add solution for godot if it exists
    if os.path.exists(env["godot_source_root"]):
        projects = [os.path.join(env["godot_source_root"], "godot.vcxproj")] + projects 

    # generate single solution containing all projects
    default_args += SConstructCommon.generate_vs_solution(env, original_args, env["solution_name"], projects)
else:
    print("skipping vsproj generation")

# Add all default targets as default args so they actually get built when scons runs
env.Default(*default_args)
