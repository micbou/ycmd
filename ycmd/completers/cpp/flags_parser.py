# Copyright (C) 2017 ycmd contributors
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


import os
try:
  import itertools.izip as zip
except ImportError:
  pass
import re


# --sysroot= must be before --sysroot) because the latter is a prefix of the
# former (and the algorithm checks prefixes)
PATH_FLAGS = [ '-isystem',
               '-I',
               '-iquote',
               '-isysroot',
               '--sysroot=',
               '--sysroot',
               '-gcc-toolchain',
               '-include',
               '-include-pch',
               '-iframework',
               '-F',
               '-imacros',
               '/I' ]


# We need to remove --fcolor-diagnostics because it will cause shell escape
# sequences to show up in editors, which is bad. See Valloric/YouCompleteMe#1421
STATE_FLAGS_TO_SKIP = [ '-c',
                        '-MP',
                        '-MD',
                        '-MMD',
                        '--fcolor-diagnostics' ]

# The -M* flags spec:
#   https://gcc.gnu.org/onlinedocs/gcc-4.9.0/gcc/Preprocessor-Options.html
VALUED_FLAGS_TO_SKIP = [ '-MF',
                         '-MT',
                         '-MQ',
                         '-o',
                         '--serialize-diagnostics',
                         '-Xclang' ]

VALUED_FLAGS = VALUED_FLAGS_TO_SKIP + PATH_FLAGS + [ '-x' ]

# Use a regex to correctly detect c++/c language for both versioned and
# non-versioned compiler executable names suffixes
# (e.g., c++, g++, clang++, g++-4.9, clang++-3.7, c++-10.2 etc).
# See Valloric/ycmd#266
CPP_COMPILER_REGEX = re.compile( r'\+\+(-\d+(\.\d+){0,2})?$' )

CL_COMPILER_REGEX = re.compile( r'(clang-cl|cl)(\.exe)?$', re.IGNORECASE )


class FlagsParser( object ):

  def __init__( self, flags, working_directory ):
    self._flags = flags
    self._working_directory = working_directory
    self._compiler = None
    self._has_already_parsed_option = False
    self._has_windows_option = False
    self._should_skip_next_flag = False


  def Parse( self ):
    new_flags = []

    for current_flag, next_flag in zip( self._flags,
                                        self._flags[ 1: ] + [ None ] ):
      if self._should_skip_next_flag:
        self._should_skip_next_flag = False
        continue

      is_windows_option = _IsWindowsOption( current_flag )
      if is_windows_option:
        self._has_windows_option = True

      if is_windows_option or _IsUnixOption( current_flag ):
        new_flags.extend( self._ParseOption( current_flag, next_flag ) )

      if self._has_already_parsed_option:
        continue

      if next_flag and not _IsOption( next_flag ):
        continue

      # We assume this flag is the compiler.
      self._compiler = current_flag

    return ( _GetFlagsForCompiler( self._compiler, self._has_windows_option ) +
             new_flags )


  def _ParseOption( self, option, next_flag ):
    self._has_already_parsed_option = True

    option, value = _GetValueFromOption( option, next_flag )

    if not _IsAcceptedOption( option ):
      if next_flag == value:
        self._should_skip_next_flag = True
      return []

    if _IsPathOption( option ):
      abs_path = value
      if not abs_path:
        if not next_flag:
          return []
        self._should_skip_next_flag = True
        abs_path = next_flag

      abs_path = self._ConvertToAbsolutePath( abs_path )

      if not os.path.exists( abs_path ):
        self._should_skip_next_flag = True
        return []

      return [ option, abs_path ]

    return [ option + value ]


  def _ConvertToAbsolutePath( self, relative_path ):
    if os.path.isabs( relative_path ):
      return os.path.normpath( relative_path )
    return os.path.normpath( os.path.join( self._working_directory,
                                           relative_path ) )


def _GetFlagsForCompiler( compiler, has_windows_flag ):
  if not compiler:
    if has_windows_flag:
      return [ '--driver-mode=cl' ]
    return []
  # Since libclang does not deduce the language from the compiler name, we
  # explicitely set the language to C++ if the compiler is a C++ one (g++,
  # clang++, etc.). Otherwise, we let libclang guess the language from the file
  # extension. This handles the case where the .h extension is used for C++
  # headers.
  if CPP_COMPILER_REGEX.search( compiler ):
    return [ compiler, '-x', 'c++' ]
  # Libclang does not automatically switch to MSVC mode if a CL-like compiler is
  # used.
  if CL_COMPILER_REGEX.search( compiler ):
    return [ compiler, '--driver-mode=cl' ]
  return [ compiler ]


def _IsOption( flag ):
  return _IsUnixOption( flag ) or _IsWindowsOption( flag )


def _IsUnixOption( flag ):
  return flag.startswith( '-' )


def _IsWindowsOption( flag ):
  return flag.startswith( '/' ) and not os.path.exists( flag )


def _IsPathOption( option ):
  for path_flag in PATH_FLAGS:
    if option.startswith( path_flag ):
      return True
  return False


def _IsAcceptedOption( option ):
  return option not in STATE_FLAGS_TO_SKIP + VALUED_FLAGS_TO_SKIP


def _GetValueFromOption( option, next_flag ):
  for valued_flag in VALUED_FLAGS:
    if option.startswith( valued_flag ):
      value = option[ len( valued_flag ): ]
      if not value:
        return valued_flag, next_flag
      return valued_flag, value
  return option, ''
