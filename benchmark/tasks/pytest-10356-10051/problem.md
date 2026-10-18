Several problems have been reported against this repository. Each is described below under its own heading. Fix all of them.

## Issue 1

Consider MRO when obtaining marks for classes
When using pytest markers in two baseclasses `Foo` and `Bar`, inheriting from both of those baseclasses will lose the markers of one of those classes. This behavior is present in pytest 3-6, and I think it may as well have been intended. I am still filing it as a bug because I am not sure if this edge case was ever explicitly considered.

If it is widely understood that all markers are part of a single attribute, I guess you could say that this is just expected behavior as per MRO. However, I'd argue that it would be more intuitive to attempt to merge marker values into one, possibly deduplicating marker names by MRO.

```python
import itertools
import pytest

class BaseMeta(type):
    @property
    def pytestmark(self):
        return (
            getattr(self, "_pytestmark", []) +
            list(itertools.chain.from_iterable(getattr(x, "_pytestmark", []) for x in self.__mro__))
        )

    @pytestmark.setter
    def pytestmark(self, value):
        self._pytestmark = value


class Base(object):
    # Without this metaclass, foo and bar markers override each other, and test_dings
    # will only have one marker
    # With the metaclass, test_dings will have both
    __metaclass__ = BaseMeta

@pytest.mark.foo
class Foo(Base):
    pass


@pytest.mark.bar
class Bar(Base):
    pass

class TestDings(Foo, Bar):
    def test_dings(self):
        # This test should have both markers, foo and bar.
        # In practice markers are resolved using MRO (so foo wins), unless the
        # metaclass is applied
        pass
```

I'd expect `foo` and `bar` to be markers for `test_dings`, but this only actually is the case with this metaclass.

Please note that the repro case is Python 2/3 compatible excluding how metaclasses are added to `Base` (this needs to be taken care of to repro this issue on pytest 6)
Consider MRO when obtaining marks for classes
When using pytest markers in two baseclasses `Foo` and `Bar`, inheriting from both of those baseclasses will lose the markers of one of those classes. This behavior is present in pytest 3-6, and I think it may as well have been intended. I am still filing it as a bug because I am not sure if this edge case was ever explicitly considered.

If it is widely understood that all markers are part of a single attribute, I guess you could say that this is just expected behavior as per MRO. However, I'd argue that it would be more intuitive to attempt to merge marker values into one, possibly deduplicating marker names by MRO.

```python
import itertools
import pytest

class BaseMeta(type):
    @property
    def pytestmark(self):
        return (
            getattr(self, "_pytestmark", []) +
            list(itertools.chain.from_iterable(getattr(x, "_pytestmark", []) for x in self.__mro__))
        )

    @pytestmark.setter
    def pytestmark(self, value):
        self._pytestmark = value


class Base(object):
    # Without this metaclass, foo and bar markers override each other, and test_dings
    # will only have one marker
    # With the metaclass, test_dings will have both
    __metaclass__ = BaseMeta

@pytest.mark.foo
class Foo(Base):
    pass


@pytest.mark.bar
class Bar(Base):
    pass

class TestDings(Foo, Bar):
    def test_dings(self):
        # This test should have both markers, foo and bar.
        # In practice markers are resolved using MRO (so foo wins), unless the
        # metaclass is applied
        pass
```

I'd expect `foo` and `bar` to be markers for `test_dings`, but this only actually is the case with this metaclass.

Please note that the repro case is Python 2/3 compatible excluding how metaclasses are added to `Base` (this needs to be taken care of to repro this issue on pytest 6)
Fix missing marks when inheritance from multiple classes

<!--
Thanks for submitting a PR, your contribution is really appreciated!

Here is a quick checklist that should be present in PRs.

- [] Include documentation when adding new features.
- [ ] Include new tests or update existing tests when applicable.
- [X] Allow maintainers to push and squash when merging my commits. Please uncheck this if you prefer to squash the commits yourself.

If this change fixes an issue, please:

- [x] Add text like ``closes #XYZW`` to the PR description and/or commits (where ``XYZW`` is the issue number). See the [github docs](https://help.github.com/en/github/managing-your-work-on-github/linking-a-pull-request-to-an-issue#linking-a-pull-request-to-an-issue-using-a-keyword) for more information.

Unless your change is trivial or a small documentation fix (e.g., a typo or reword of a small section) please:

- [x] Create a new changelog file in the `changelog` folder, with a name like `<ISSUE NUMBER>.<TYPE>.rst`. See [changelog/README.rst](https://github.com/pytest-dev/pytest/blob/main/changelog/README.rst) for details.

  Write sentences in the **past or present tense**, examples:

  * *Improved verbose diff output with sequences.*
  * *Terminal summary statistics now use multiple colors.*

  Also make sure to end the sentence with a `.`.

- [x] Add yourself to `AUTHORS` in alphabetical order.
-->

## Issue 2

caplog.get_records and caplog.clear conflict
# Description

`caplog.get_records()` gets decoupled from actual caplog records when `caplog.clear()` is called. As a result, after `caplog.clear()` is called, `caplog.get_records()` is frozen: it does not get cleared, nor does it get new records.

During test set up it is [set to the same list](https://github.com/pytest-dev/pytest/blob/28e8c8582ea947704655a3c3f2d57184831336fd/src/_pytest/logging.py#L699) as `caplog.records`, but the latter gets [replaced rather than cleared](https://github.com/pytest-dev/pytest/blob/28e8c8582ea947704655a3c3f2d57184831336fd/src/_pytest/logging.py#L345) in `caplog.clear()`, which diverges the two objects.

# Reproductive example
```python
import logging

def test(caplog) -> None:
    def verify_consistency() -> None:
        assert caplog.get_records("call") == caplog.records

    verify_consistency()
    logging.warning("test")
    verify_consistency()
    caplog.clear()
    verify_consistency()  # fails: assert [<LogRecord: ...y, 8, "test">] == []
```

# Environment details
Arch Linux, Python 3.9.10:
```
Package    Version
---------- -------
attrs      21.4.0
iniconfig  1.1.1
packaging  21.3
pip        22.0.4
pluggy     1.0.0
py         1.11.0
pyparsing  3.0.8
pytest     7.1.1
setuptools 60.10.0
tomli      2.0.1
wheel      0.37.1
```