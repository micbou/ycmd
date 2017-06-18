if [ "${YCM_BENCHMARK}" == "true" ]; then
  ./benchmark.py --build-dir build
  cd build/ycm/benchmarks
  export LD_LIBRARY_PATH="${TRAVIS_BUILD_DIR}"
  valgrind --suppressions=${TRAVIS_BUILD_DIR}/valgrind-python.supp ./ycm_core_benchmarks
else
  ./run_tests.py
fi
