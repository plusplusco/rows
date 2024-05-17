# Contributing

## Creating your development environment

The preferred way is to create a virtualenv (you can do by using virtualenv,
virtualenvwrapper, pyenv or whatever tool you'd like).

Create the virtualenv:

```bash
mkvirtualenv rows
```

Install all plugins' dependencies:

```bash
pip install --editable .[all]
```

Install development dependencies:

```bash
pip install -r requirements-development.txt
```

## Running the tests

There are two possible ways of running the tests: on your own virtualenv or for
each Python version.

For the PostgreSQL plugin you're going to need a PostgreSQL server running and
must set the `POSTGRESQL_URI` environment variable. If you have docker
installed you can easily create a container running PostgreSQL with the
provided `compose.yml` by running:

```bash
docker compose -p rows up -d
```

### Running on your virtualenv

```bash
nosetests -dsv --with-yanc --with-coverage --cover-package rows tests/*.py
```

### Running for all Python versions

Run tests:

```bash
make test
```

or (if you don't have `make`):

```bash
tox
```

you can also run tox against an specific python version:

```bash
tox -e py27
tox -e py35
```

*tox known issues* : running tox with py27 environ may raise InvocationError in
non Linux environments. To avoid it you may rebuild tox environment in every
run with `tox -e py27 -r` or if you want to run nosetests directly (see last
section).

## Running PostgreSQL tests

A PostgreSQL server is needed to run the PostgreSQL plugin tests. You can use
[Docker](https://docker.io/) to easily run a PostgreSQL server, but can also
use your own method to run it. The `POSTGRESQL_URI` environment variable need
to be se so you can run the tests.

Running the PostgreSQL container using docker compose, set the environment
variable and run the PostgreSQL-specific tests:

```bash
docker compose -p rows up -d
export POSTGRESQL_URI=postgres://postgres:postgres@127.0.0.1:42001/rows
nosetests -dsv --with-yanc --with-coverage --cover-package rows tests/tests_plugin_postgresql.py
```


## Generating the documentation

Just run:

```bash
make docs
```

And check the `docs-build/` directory.

You can also serve it via HTTP:

```bash
make docs-serve
```


## Releasing new versions

```
# X = next version number

# *** Create the release branch
git checkout -b release/X
# Update docs/changelog.md & commit
# Change version number in `setup.py` and `rows/__init__.py` & commit

# *** Merge into master, tag and test it
git checkout master && git merge --no-ff release/X
git tag -a X
make test
# STOP HERE IF TESTS FAIL

# *** Release to PyPI and docs to GitHub Pages
make release
make docs-upload

# *** Update remote repository
git branch -d release/X
git push turicas master
git checkout develop
# Change version number in `setup.py` and `rows/__init__.py` to the next
# dev version (eg: if released 0.4.1, then change to 0.4.2dev0) & commit
git push turicas develop
```
