# Copyright (C) 2011, 2012 Google Inc.
#
# This file is part of ycmd.
#
# ycmd is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# ycmd is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with ycmd.  If not, see <http://www.gnu.org/licenses/>.

from __future__ import unicode_literals
from __future__ import print_function
from __future__ import division
from __future__ import absolute_import
from future import standard_library
standard_library.install_aliases()
from builtins import *  # noqa

import ycm_core
import os
import inspect
from future.utils import PY2, native
from ycmd import extra_conf_store
from ycmd.completers.cpp.flags_parser import FlagsParser
from ycmd.utils import ( ToCppStringCompatible, OnMac, OnWindows, ToUnicode,
                         ToBytes, PathsToAllParentFolders )
from ycmd.responses import NoExtraConfDetected


# List of file extensions to be considered "header" files and thus not present
# in the compilation database. The logic will try and find an associated
# "source" file (see SOURCE_EXTENSIONS below) and use the flags for that.
HEADER_EXTENSIONS = [ '.h', '.hxx', '.hpp', '.hh' ]

# List of file extensions which are considered "source" files for the purposes
# of heuristically locating the flags for a header file.
SOURCE_EXTENSIONS = [ '.cpp', '.cxx', '.cc', '.c', '.m', '.mm' ]

EMPTY_FLAGS = {
  'flags': [],
}

CLANG_INCLUDES_PATH = os.path.join( os.path.dirname( ycm_core.__file__ ),
                                    'clang_includes' )


class NoCompilationDatabase( Exception ):
  pass


class Flags( object ):
  """Keeps track of the flags necessary to compile a file.
  The flags are loaded from user-created python files (hereafter referred to as
  'modules') that contain a method FlagsForFile( filename )."""

  def __init__( self ):
    # It's caches all the way down...
    self.flags_for_file = {}
    self.mac_include_paths = _MacIncludePaths()
    self.no_extra_conf_file_warning_posted = False

    # We cache the compilation database for any given source directory
    # Keys are directory names and values are ycm_core.CompilationDatabase
    # instances or None. Value is None when it is known there is no compilation
    # database to be found for the directory.
    self.compilation_database_dir_map = dict()

    # Sometimes we don't actually know what the flags to use are. Rather than
    # returning no flags, if we've previously found flags for a file in a
    # particular directory, return them. These will probably work in a high
    # percentage of cases and allow new files (which are not yet in the
    # compilation database) to receive at least some flags.
    # Keys are directory names and values are ycm_core.CompilationInfo
    # instances. Values may not be None.
    self.file_directory_heuristic_map = dict()


  def FlagsForFile( self,
                    filename,
                    add_extra_clang_flags = True,
                    client_data = None ):

    # The try-catch here is to avoid a synchronisation primitive. This method
    # may be called from multiple threads, and python gives us
    # 1-python-statement synchronisation for "free" (via the GIL)
    try:
      return self.flags_for_file[ filename ]
    except KeyError:
      pass

    module = extra_conf_store.ModuleForSourceFile( filename )
    try:
      results = self._GetFlagsFromExtraConfOrDatabase( module,
                                                       filename,
                                                       client_data )
    except NoCompilationDatabase:
      if not self.no_extra_conf_file_warning_posted:
        self.no_extra_conf_file_warning_posted = True
        raise NoExtraConfDetected
      return None

    if not results or not results.get( 'flags_ready', True ):
      return None

    flags, working_directory = _ExtractFlagsListAndWorkingDirectory( results )
    if not flags or not working_directory:
      return None

    flags = FlagsParser( flags, working_directory ).Parse()

    if add_extra_clang_flags:
      flags = _ExtraClangFlags( flags )

    sanitized_flags = PrepareFlagsForClang( flags )

    if results.get( 'do_cache', True ):
      self.flags_for_file[ filename ] = sanitized_flags
    return sanitized_flags


  def _GetFlagsFromExtraConfOrDatabase( self, module, filename, client_data ):
    if not module:
      return self._GetFlagsFromCompilationDatabase( filename )
    return _CallExtraConfFlagsForFile( module, filename, client_data )


  def UserIncludePaths( self, filename, client_data ):
    flags = [ ToUnicode( x ) for x in
              self.FlagsForFile( filename, client_data = client_data ) ]

    quoted_include_paths = [ os.path.dirname( filename ) ]
    include_paths = []

    if flags:
      quote_flag = '-iquote'
      path_flags = [ '-isystem', '-I' ]

      try:
        it = iter( flags )
        for flag in it:
          flag_len = len( flag )
          if flag.startswith( quote_flag ):
            quote_flag_len = len( quote_flag )
            # Add next flag to the include paths if current flag equals to
            # '-iquote', or add remaining string otherwise.
            quoted_include_paths.append( next( it )
                                         if flag_len == quote_flag_len
                                         else flag[ quote_flag_len: ] )
          else:
            for path_flag in path_flags:
              if flag.startswith( path_flag ):
                path_flag_len = len( path_flag )
                include_paths.append( next( it )
                                      if flag_len == path_flag_len
                                      else flag[ path_flag_len: ] )
                break
      except StopIteration:
        pass

    return ( [ x for x in quoted_include_paths if x ],
             [ x for x in include_paths if x ] )


  def Clear( self ):
    self.flags_for_file.clear()
    self.compilation_database_dir_map.clear()
    self.file_directory_heuristic_map.clear()


  def _GetFlagsFromCompilationDatabase( self, file_name ):
    file_dir = os.path.dirname( file_name )
    file_root, file_extension = os.path.splitext( file_name )

    database = self.FindCompilationDatabase( file_dir )
    compilation_info = _GetCompilationInfoForFile( database,
                                                   file_name,
                                                   file_extension )

    if not compilation_info:
      # Note: Try-catch here synchronises access to the cache (as this can be
      # called from multiple threads).
      try:
        # We previously saw a file in this directory. As a guess, just
        # return the flags for that file. Hopefully this will at least give some
        # meaningful compilation.
        compilation_info = self.file_directory_heuristic_map[ file_dir ]
      except KeyError:
        # No cache for this directory and there are no flags for this file in
        # the database.
        return EMPTY_FLAGS

    # If this is the first file we've seen in path file_dir, cache the
    # compilation_info for it in case we see a file in the same dir with no
    # flags available.
    # The following updates file_directory_heuristic_map if and only if file_dir
    # isn't already there. This works around a race condition where 2 threads
    # could be executing this method in parallel.
    self.file_directory_heuristic_map.setdefault( file_dir, compilation_info )

    return {
      'flags': compilation_info.compiler_flags_,
      'working_directory': compilation_info.compiler_working_dir_
    }


  # Return a compilation database object for the supplied path. Raises
  # NoCompilationDatabase if no compilation database can be found.
  def FindCompilationDatabase( self, file_dir ):
    # We search up the directory hierarchy, to first see if we have a
    # compilation database already for that path, or if a compile_commands.json
    # file exists in that directory.
    for folder in PathsToAllParentFolders( file_dir ):
      # Try/catch to syncronise access to cache
      try:
        database = self.compilation_database_dir_map[ folder ]
        if database:
          return database

        raise NoCompilationDatabase
      except KeyError:
        pass

      compile_commands = os.path.join( folder, 'compile_commands.json' )
      if os.path.exists( compile_commands ):
        database = ycm_core.CompilationDatabase( folder )

        if database.DatabaseSuccessfullyLoaded():
          self.compilation_database_dir_map[ folder ] = database
          return database

    # Nothing was found. No compilation flags are available.
    # Note: we cache the fact that none was found for this folder to speed up
    # subsequent searches.
    self.compilation_database_dir_map[ file_dir ] = None
    raise NoCompilationDatabase


def _ExtractFlagsListAndWorkingDirectory( flags_for_file_output ):
  flags = [ ToUnicode( x ) for x in flags_for_file_output.get( 'flags', [] ) ]
  working_directory = flags_for_file_output.get( 'working_directory' )
  return flags, working_directory


def _CallExtraConfFlagsForFile( module, filename, client_data ):
  # We want to ensure we pass a native py2 `str` on py2 and a native py3 `str`
  # (unicode) object on py3. That's the API we provide.
  # In a vacuum, always passing a unicode object (`unicode` on py2 and `str` on
  # py3) would be better, but we can't do that because that would break all the
  # ycm_extra_conf files already out there that expect a py2 `str` object on
  # py2, and WE DO NOT BREAK BACKWARDS COMPATIBILITY.
  # Hindsight is 20/20.
  if PY2:
    filename = native( ToBytes( filename ) )
  else:
    filename = native( ToUnicode( filename ) )

  # For the sake of backwards compatibility, we need to first check whether the
  # FlagsForFile function in the extra conf module even allows keyword args.
  if inspect.getargspec( module.FlagsForFile ).keywords:
    flags_for_file = module.FlagsForFile( filename, client_data = client_data )
  else:
    flags_for_file = module.FlagsForFile( filename )
  flags_for_file[ 'working_directory' ] = os.path.dirname( module.__file__ )
  return flags_for_file


def PrepareFlagsForClang( flags ):
  vector = ycm_core.StringVector()
  for flag in flags:
    vector.append( ToCppStringCompatible( flag ) )
  return vector


# There are 2 ways to get a development enviornment (as standard) on OS X:
#  - install XCode.app, or
#  - install the command-line tools (xcode-select --install)
#
# Most users have xcode installed, but in order to be as compatible as
# possible we consider both possible installation locations
MAC_CLANG_TOOLCHAIN_DIRS = [
  '/Applications/Xcode.app/Contents/Developer/Toolchains/'
    'XcodeDefault.xctoolchain',
  '/Library/Developer/CommandLineTools'
]


# Returns a list containing the supplied path as a suffix of each of the known
# Mac toolchains
def _PathsForAllMacToolchains( path ):
  return [ os.path.join( x, path ) for x in MAC_CLANG_TOOLCHAIN_DIRS ]


# Ultimately, this method exists only for testability
def _GetMacClangVersionList( candidates_dir ):
  try:
    return os.listdir( candidates_dir )
  except OSError:
    # Path might not exist, so just ignore
    return []


# Ultimately, this method exists only for testability
def _MacClangIncludeDirExists( candidate_include ):
  return os.path.exists( candidate_include )


# Add in any clang headers found in the installed toolchains. These are
# required for the same reasons as described below, but unfortuantely, these
# are in versioned directories and there is no easy way to find the "correct"
# version. We simply pick the highest version in the first toolchain that we
# find, as this is the most likely to be correct.
def _LatestMacClangIncludes():
  for path in MAC_CLANG_TOOLCHAIN_DIRS:
    # we use the first toolchain which actually contains any versions, rather
    # than trying all of the toolchains and picking the highest. We
    # favour Xcode over CommandLineTools as using Xcode is more common.
    # It might be possible to extrace this information from xcode-select, though
    # xcode-select -p does not point at the toolchain directly
    candidates_dir = os.path.join( path, 'usr', 'lib', 'clang' )
    versions = _GetMacClangVersionList( candidates_dir )

    for version in reversed( sorted( versions ) ):
      candidate_include = os.path.join( candidates_dir, version, 'include' )
      if _MacClangIncludeDirExists( candidate_include ):
        return [ candidate_include ]

  return []




def _MacIncludePaths():
  flags = []
  if not OnMac():
    return flags

  # These are the standard header search paths that clang will use on Mac BUT
  # libclang won't, for unknown reasons. We add these paths when the user is on
  # a Mac because if we don't, libclang would fail to find <vector> etc.  This
  # should be fixed upstream in libclang, but until it does, we need to help
  # users out.
  # See the following for details:
  #  - Valloric/YouCompleteMe#303
  #  - Valloric/YouCompleteMe#2268
  for path in (
      _PathsForAllMacToolchains( 'usr/include/c++/v1' ) +
      [ '/usr/local/include' ] +
      _PathsForAllMacToolchains( 'usr/include' ) +
      [ '/usr/include', '/System/Library/Frameworks', '/Library/Frameworks' ] +
      _LatestMacClangIncludes() +
      # We include the MacOS platform SDK because some meaningful parts of the
      # standard library are located there. If users are compiling for (say)
      # iPhone.platform, etc. they should appear earlier in the include path.
      [ '/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/'
        'Developer/SDKs/MacOSX.sdk/usr/include' ] ):
    flags.extend( [ '-isystem', path ] )
  return flags


def _ExtraClangFlags( flags ):
  flags = _EnableTypoCorrection( flags )
  flags = _AddClangIncludes( flags )
  flags = _AddNoDelayedTemplateParsingFlag( flags )
  return flags


def _EnableTypoCorrection( flags ):
  """Adds the -fspell-checking flag if the -fno-spell-checking flag is not
  present"""

  # "Typo correction" (aka spell checking) in clang allows it to produce
  # hints (in the form of fix-its) in the case of certain diagnostics. A common
  # example is "no type named 'strng' in namespace 'std'; Did you mean
  # 'string'? (FixIt)". This is enabled by default in the clang driver (i.e. the
  # 'clang' binary), but is not when using libclang (as we do). It's a useful
  # enough feature that we just always turn it on unless the user explicitly
  # turned it off in their flags (with -fno-spell-checking).
  if '-fno-spell-checking' in flags:
    return flags

  flags.append( '-fspell-checking' )
  return flags


def _AddClangIncludes( flags ):
  # -resource-dir flag is not available in CL mode so we use the /I flag
  # instead.
  if not _IsInClMode( flags ):
    return flags + [ '-resource-dir=' + CLANG_INCLUDES_PATH ]
  return flags + [ '/I', os.path.join( CLANG_INCLUDES_PATH, 'include' ) ]


def _AddNoDelayedTemplateParsingFlag( flags ):
  # On Windows, parsing of templates is delayed until instantiation time.
  # This makes GetType and GetParent commands fail to return the expected
  # result when the cursor is in a template.
  # Using the -fno-delayed-template-parsing flag disables this behavior.
  # See http://clang.llvm.org/extra/PassByValueTransform.html#note-about-delayed-template-parsing # noqa
  # for an explanation of the flag and
  # https://code.google.com/p/include-what-you-use/source/detail?r=566
  # for a similar issue.
  if OnWindows() and not _IsInClMode( flags ):
    flags.append( '-fno-delayed-template-parsing' )
  return flags


# Find the compilation info structure from the supplied database for the
# supplied file. If the source file is a header, try and find an appropriate
# source file and return the compilation_info for that.
def _GetCompilationInfoForFile( database, file_name, file_extension ):
  # The compilation_commands.json file generated by CMake does not have entries
  # for header files. So we do our best by asking the db for flags for a
  # corresponding source file, if any. If one exists, the flags for that file
  # should be good enough.
  if file_extension in HEADER_EXTENSIONS:
    for extension in SOURCE_EXTENSIONS:
      replacement_file = os.path.splitext( file_name )[ 0 ] + extension
      compilation_info = database.GetCompilationInfoForFile(
        replacement_file )
      if compilation_info and compilation_info.compiler_flags_:
        return compilation_info

    # No corresponding source file was found, so we can't generate any flags for
    # this header file.
    return None

  # It's a source file. Just ask the database for the flags.
  compilation_info = database.GetCompilationInfoForFile( file_name )
  if compilation_info.compiler_flags_:
    return compilation_info

  return None


def _IsInClMode( flags ):
  return '--driver-mode=cl' in flags
