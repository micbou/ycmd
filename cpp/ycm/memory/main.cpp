// Copyright (C) 2017 ycmd contributors
//
// This file is part of ycmd.
//
// ycmd is free software: you can redistribute it and/or modify
// it under the terms of the GNU General Public License as published by
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.
//
// ycmd is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
// GNU General Public License for more details.
//
// You should have received a copy of the GNU General Public License
// along with ycmd.  If not, see <http://www.gnu.org/licenses/>.

#include <iostream>
#include <boost/python.hpp>
#include <chrono>
#include <random>
#include <thread>
#include <vector>
#if defined( _WIN32 )
#include <windows.h>
#include <psapi.h>
#elif defined( __linux__ )
#include <fstream>
#include <string>
#include <unistd.h>
#elif defined( __APPLE__ ) && defined( __MACH__ )
#include <mach/mach.h>
#endif

#include "CandidateRepository.h"

namespace YouCompleteMe {

std::string RandomString( size_t length )
{
  auto randchar = []() -> char
  {
    const char charset[] =
      "0123456789"
      "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
      "abcdefghijklmnopqrstuvwxyz";
    const size_t max_index = sizeof(charset) - 1;
    return charset[ rand() % max_index ];
  };
  std::string str( length, 0 );
  std::generate_n( str.begin(), length, randchar );
  return str;
}


size_t GetMemoryUsage() {
#if defined( _WIN32 )
    PROCESS_MEMORY_COUNTERS_EX memory_counter;
    GetProcessMemoryInfo( GetCurrentProcess(),
                          ( PROCESS_MEMORY_COUNTERS* ) &memory_counter,
                          sizeof( memory_counter ) );
    return memory_counter.PrivateUsage;
#elif defined( __linux__ )
    size_t total_program_size, resident_set_size;
    std::ifstream statm( "/proc/self/statm" );
    if ( !statm.is_open() )
      return 0;
    statm >> total_program_size >> resident_set_size;
    return resident_set_size * sysconf( _SC_PAGESIZE );
#elif defined( __APPLE__ ) && defined( __MACH__ )
    struct mach_task_basic_info info;
    mach_msg_type_number_t info_count = MACH_TASK_BASIC_INFO_COUNT;
    if ( task_info( mach_task_self(),
                    MACH_TASK_BASIC_INFO,
                    ( task_info_t ) &info,
                    &info_count ) != KERN_SUCCESS )
      return 0;
    return info.resident_size;
#else
    return 0;
#endif
}

} // namespace YouCompleteMe

using namespace YouCompleteMe;


int main() {
  Py_Initialize();
  // Necessary because of usage of the ReleaseGil class.
  PyEval_InitThreads();

  size_t number_of_strings = 100000;
  unsigned average_candidate_width = 20;
  size_t memory_usage_with_no_candidates = GetMemoryUsage();

  {
    std::vector< std::string > strings;
    for ( size_t i = 0; i < number_of_strings; ++i )
      strings.push_back( RandomString( average_candidate_width ));
    CandidateRepository::Instance().GetCandidatesForStrings( strings );
  }

  unsigned number_of_candidates =
     CandidateRepository::Instance().NumStoredCandidates();

  size_t memory_usage_with_candidates = GetMemoryUsage();
  size_t memory_usage_by_candidate =
    ( memory_usage_with_candidates - memory_usage_with_no_candidates ) /
    number_of_candidates;

  CandidateRepository::Instance().ClearCandidates();

  size_t memory_usage_after_clearing = GetMemoryUsage();

  std::cout << "Total memory usage:\n"
            << " - with no candidate stored: "
            << memory_usage_with_no_candidates << " B\n"
            << " - with " << number_of_candidates << " candidates stored: "
            << memory_usage_with_candidates << " B\n"
            << " - after clearing candidates: "
            << memory_usage_after_clearing << " B\n";

  std::cout << "Candidate memory usage: "
            << memory_usage_by_candidate << " B\n";
}
