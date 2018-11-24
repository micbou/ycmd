if [ "${YCM_PACKAGE}" == "true" ]; then
  ./build.py --clang-completer --cs-completer --go-completer --java-completer --rust-completer --ts-completer
elif [ "${YCM_BENCHMARK}" == "true" ]; then
  ./benchmark.py
elif [ "${YCM_CLANG_TIDY}" == "true" ]; then
  ./build.py --clang-completer --clang-tidy --quiet --no-regex
else
  ./run_tests.py
fi
