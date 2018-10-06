# Copyright (C) 2018 ycmd contributors
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

project( ycm_fake_clang )
cmake_minimum_required( VERSION 2.8 )

include_directories( ${ycm_core_SOURCE_DIR} )

add_executable( ${PROJECT_NAME} main.cpp )

# Always use system libclang on macOS.
# if ( APPLE )
#   find_library( LIBCLANG_FAKE_TARGET
#                 NAMES
#                 clang
#                 PATHS
#                 /Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/lib
#                 /Library/Developer/CommandLineTools/usr/lib )
# else()
#   set( LIBCLANG_FAKE_TARGET ${LIBCLANG_TARGET} )
# endif()

target_link_libraries( ${PROJECT_NAME}
                       ${LIBCLANG_FAKE_TARGET} )

if ( EXTERNAL_LIBCLANG_PATH AND APPLE AND NOT USE_SYSTEM_LIBCLANG)
  get_filename_component(EXTRA_LIB_PATH ${EXTERNAL_LIBCLANG_PATH} DIRECTORY)

  set_target_properties(${PROJECT_NAME}
    PROPERTIES LINK_FLAGS "-Wl,-rpath,${EXTRA_LIB_PATH}")

  add_custom_command( TARGET ${PROJECT_NAME}
                      POST_BUILD
                      COMMAND install_name_tool
                      "-change"
                      "@rpath/libclang.dylib"
                      "@loader_path/libclang.dylib"
                      "$<TARGET_FILE:${PROJECT_NAME}>"
                    )
endif()

# Build ycm_fake_clang in ycmd root folder.
if ( MSVC )
  foreach( OUTPUTCONFIG ${CMAKE_CONFIGURATION_TYPES} )
    string( TOUPPER ${OUTPUTCONFIG} OUTPUTCONFIG )
    set_target_properties( ${PROJECT_NAME} PROPERTIES
      RUNTIME_OUTPUT_DIRECTORY_${OUTPUTCONFIG} ${PROJECT_SOURCE_DIR}/../../.. )
  endforeach()
else()
  set_target_properties( ${PROJECT_NAME} PROPERTIES
    RUNTIME_OUTPUT_DIRECTORY ${PROJECT_SOURCE_DIR}/../../.. )
endif()
