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

project( ycm_core_benchmarks )
cmake_minimum_required( VERSION 2.8 )

# We don't want to test the benchmark library.
set( BENCHMARK_ENABLE_TESTING
     OFF CACHE BOOL "Enable testing of the benchmark library" )
set( BUILD_SHARED_LIBS OFF )

add_subdirectory( benchmark )
set( BENCHMARK_INCLUDE_DIRS ${benchmark_SOURCE_DIR}/include )
set( BENCHMARK_LIBRARIES benchmark )

include_directories( ${ycm_core_SOURCE_DIR}
                     ${BENCHMARK_INCLUDE_DIRS} )

file( GLOB_RECURSE SOURCES *.h *.cpp )

# We don't want benchmark sources in this target.
file( GLOB_RECURSE to_remove benchmark/*.h benchmark/*.cpp CMakeFiles/*.cpp
                             benchdata/*.cpp benchdata/*.h )

if( to_remove )
  list( REMOVE_ITEM SOURCES ${to_remove} )
endif()

add_executable( ${PROJECT_NAME}
                ${SOURCES} )

if( MSVC )
  # Build benchmark and ycm_core_benchmarks targets in cmake ycm/benchmarks
  # folder.
  foreach( OUTPUTCONFIG ${CMAKE_CONFIGURATION_TYPES} )
    string( TOUPPER ${OUTPUTCONFIG} OUTPUTCONFIG )
    set_target_properties( ${BENCHMARK_LIBRARIES} PROPERTIES
      RUNTIME_OUTPUT_DIRECTORY_${OUTPUTCONFIG} ${PROJECT_BINARY_DIR} )
    set_target_properties( ${PROJECT_NAME} PROPERTIES
      RUNTIME_OUTPUT_DIRECTORY_${OUTPUTCONFIG} ${PROJECT_BINARY_DIR} )
  endforeach()
endif()

target_link_libraries( ${PROJECT_NAME}
                       ${Boost_LIBRARIES}
                       ycm_core
                       ${BENCHMARK_LIBRARIES} )

if ( NOT CMAKE_GENERATOR_IS_XCODE )
  # The benchmark executable expects a "benchdata" dir in its working directory.
  # Why?  Because there's NO reliable, cross-platform way of getting the
  # directory in which the executable is located.
  add_custom_target( copy_benchdata
                     COMMAND cmake -E copy_directory
                     ${CMAKE_CURRENT_SOURCE_DIR}/benchdata
                     ${CMAKE_CURRENT_BINARY_DIR}/benchdata )
else()
  add_custom_target( copy_benchdata
                     COMMAND cmake -E copy_directory
                     ${CMAKE_CURRENT_SOURCE_DIR}/benchdata
                     ${CMAKE_CURRENT_BINARY_DIR}/Debug/benchdata
                     COMMAND cmake -E copy_directory
                     ${CMAKE_CURRENT_SOURCE_DIR}/benchdata
                     ${CMAKE_CURRENT_BINARY_DIR}/Release/benchdata )

endif()

add_dependencies( ${PROJECT_NAME} copy_benchdata )
