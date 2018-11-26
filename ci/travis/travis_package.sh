python -m venv venv
venv/bin/pip install pyinstaller
venv/bin/pyinstaller package.spec
tar -zcvf ycmd-linux-64.tar.gz -C ${TRAVIS_BUILD_DIR}/dist ycmd

YCMD_LAST_VERSION=$(git describe --tags --match *.*.*)
echo $YCMD_LAST_VERSION

export YCMD_VERSION=$(python -c "from ycmd import __version__; print(__version__)")
echo $YCMD_VERSION

if [ -z "${TRAVIS_TAG}" ]; then
  export YCM_RELEASE_DEPLOYMENT=false
  export TRAVIS_TAG=dev

  # Travis do a shallow clone by default. We need a full clone to push the tag.
  git fetch --unshallow
  git tag -f ${TRAVIS_TAG}
  git push -f https://${YCMD_GITHUB_KEY}@github.com/micbou/ycmd ${TRAVIS_TAG}
else
  export YCM_RELEASE_DEPLOYMENT=true
fi
