if [ "${YCM_PACKAGE}" == "true" ]; then
  python -m venv venv
  venv/bin/pip install pyinstaller
  venv/bin/pyinstaller package.spec
  tar -zcvf ycmd-linux-64.tar.gz ${TRAVIS_BUILD_DIR}/dist/ycmd

  if [ -z "${TRAVIS_TAG}" ]; then
    export YCM_RELEASE_DEPLOYMENT=false
    export TRAVIS_TAG=dev
  else
    export YCM_RELEASE_DEPLOYMENT=true
  fi
  echo "TRAVIS_TAG: ${TRAVIS_TAG}"
  echo "YCM_PACKAGE: ${YCM_PACKAGE}"
  echo "YCM_RELEASE_DEPLOYMENT: ${YCM_RELEASE_DEPLOYMENT}"
fi
