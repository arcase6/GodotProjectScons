# GodotProjectScons
Scons files for quickly adding extensions to project with minimal additional work and generate .vsproj files. Tries to keep all boilerplate written for scons in a single SConstruct file

This is still a work in progress. In order to use place the SConstruct and SConstructCommon files in your project root. Place SCSub at the root of any C++ GDExtension projects. You do not need to write a .gdextension file. Scons will write it for you.

Run scons vsproj=yes to compile all gd extensions in your project with SCSub and generate one vs project per extension. A vs solution will be generated that lets you view godot, godot-cpp, and all of your project extensions in a single place.

Note that community addons tend to using SConstruct for their gdextension and will be ignored. You can add a SCSub file and delete their SConstruct file if you want to use this system instead.

Currently their are still issues with project generation. It works really well for setting up the project and getting intellisense but there are still issues with building from vsproj. Can't tell godot project to build or run godot from the generated solution. Also some issues with mono since gdextension does no have a mono configuration.

Also worth noting that I want to move the ability to configure how binaries are built a bit better from SCSub. Currently the only thing that is specified is paths for .cpp and .h files pretty much. Not too much in the way of config.

The SConscript file I made can generate .gdextension files for you. Also has options to list binaries for different platforms. I have it default to Win64 because I'm currently only developing for Win64 with options for other platforms like linux etc. Would like to actually try to use this on other platforms and see what issues come up.