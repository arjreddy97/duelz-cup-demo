Several problems have been reported against this repository. Each is described below under its own heading. Fix all of them.

## Issue 1

Pattern detection returns wrong pattern when no match found

#### Description

The `detect_pattern` method in the logreader Parser class returns an incorrect pattern when no patterns match the input line. Instead of returning `None` or raising an exception, it returns the last pattern in the iteration list.

#### Steps/Code to Reproduce

```python
import cantools.logreader

# Create a line that doesn't match any known patterns
invalid_line = "this is not a valid log format line"

# Try to detect the pattern
pattern = cantools.logreader.Parser.detect_pattern(invalid_line)
print(f"Detected pattern: {pattern}")
print(f"Pattern should be None but got: {type(pattern)}")
```

This will incorrectly return a pattern object instead of `None` when the line doesn't match any known log format patterns.

The issue affects parsing of log files where some lines might not match expected formats, causing the parser to use an inappropriate pattern for subsequent parsing operations.

## Issue 2

List command crashes when displaying messages with header_id None

#### Description

When using the `cantools list` command with `--print-all` flag on certain database files, the command crashes with a `TypeError: unsupported format string passed to NoneType.__format__` error. This happens when trying to format a `None` value for `header_id` in the message display output.

#### Steps/Code to Reproduce

```bash
cantools list --print-all tests/files/dbc/motohawk.dbc
```

This will produce:
```
TypeError: unsupported format string passed to NoneType.__format__
```

The same error occurs with other database formats like KCD and ARXML files when using the detailed listing functionality.

#### Expected Behavior

The command should display message information without crashing, properly handling cases where `header_id` is `None`.

#### Actual Behavior

The command crashes with a format string error when attempting to display header ID information for messages that don't have a header ID set.

## Issue 3

DID datas property returns string representation instead of list

#### Description

When accessing the `datas` property of a DID object, it returns a string representation of the data list with an extra space appended, instead of returning the actual list of data objects.

#### Steps/Code to Reproduce

```python
import cantools

# Load a CDD file
db = cantools.db.load_file('tests/files/cdd/le-example.cdd', encoding='iso-8859-1')

# Get a DID
did = db.get_did_by_name('InputOutput')

# Access the datas property
print(type(did.datas))  # Should be <class 'list'> but returns <class 'str'>
print(repr(did.datas))  # Shows string representation instead of list

# This breaks iteration over datas
for data in did.datas:
    print(data.name)  # This will iterate over characters instead of data objects
```

The `datas` property should return a list of data objects that can be iterated over and accessed normally, but instead returns a string representation making it impossible to work with the individual data elements programmatically.