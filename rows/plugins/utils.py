# coding: utf-8

# Copyright 2014-2019 Álvaro Justen <https://github.com/turicas/rows/>

#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Lesser General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.

#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Lesser General Public License for more details.

#    You should have received a copy of the GNU Lesser General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.

from __future__ import unicode_literals

import warnings
import sys

from collections import OrderedDict
from collections.abc import Mapping
from itertools import chain, islice
from os import unlink
from pathlib import Path
from textwrap import dedent as D

import six

# 'slug' and 'make_unique_name' are required here to maintain backwards compatibility
from rows.fields import get_items  # NOQA
from rows.fields import TextField, detect_types, make_header
from rows.table import FlexibleTable, Table, SQLiteTable

from rows.utils import Source
from rows.utils.query import ensure_query

if six.PY2:
    from collections import Iterator
elif six.PY3:
    from collections.abc import Iterator


def ipartition(iterable, partition_size):
    if not isinstance(iterable, Iterator):
        iterator = iter(iterable)
    else:
        iterator = iterable

    finished = False
    while not finished:
        data = []
        for _ in range(partition_size):
            try:
                data.append(next(iterator))
            except StopIteration:
                finished = True
                break
        if data:
            yield data


def _infer_fields(header, sample_rows, force_types, max_rows, import_fields, create_table_args, create_table_kwargs):
    """Inner function to detect fields and field types from a data source"""

    # autodetect field types
    # TODO: may add `type_hints` parameter to create_table so autodetection can be easier
    #       (plugins may specify some possible field types).

    # Detect field types using only the desired columns
    detected_fields = detect_types(
        header,
        sample_rows,
        skip_indexes=[
            index
            for index, field in enumerate(header)
            if field in force_types or field not in (import_fields or header)
        ],
        *create_table_args,
        **create_table_kwargs
    )
    # Check if any field was added during detecting process
    new_fields = [
        field_name
        for field_name in detected_fields.keys()
        if field_name not in header
    ]
    # Finally create the `fields` with both header and new field names,
    # based on detected fields `and force_types`
    fields = OrderedDict(
        [
            (field_name, detected_fields.get(field_name, TextField))
            for field_name in header + new_fields
        ]
    )
    fields.update(force_types)
    return fields


def create_table(
    data,
    meta=None,
    fields=None,
    skip_header=True,
    import_fields=None,
    samples=None,
    force_types=None,
    max_rows=None,
    *args,
    table_class=None,
    query=None,
    **kwargs
):
    """Create a rows.Table object based on data rows and some configurations

    - `skip_header` is only used if `fields` is set
    - `samples` is only used if `fields` is `None`. If samples=None, all data
      is filled in memory - use with caution.
    - `force_types` is only used if `fields` is `None`
    - `import_fields` can be used either if `fields` is set or not, the
      resulting fields will seek its order
    - `fields` must always be in the same order as the data
    """

    if table_class is None:
        table_class = Table

    table_rows = iter(data)
    force_types = force_types or {}
    if import_fields is not None:
        import_fields = make_header(import_fields)

    if fields is None:
        header = make_header(next(table_rows))

        if samples is not None:
            sample_rows = list(islice(table_rows, 0, samples))
            if max_rows is not None and max_rows - samples > 0:
                table_rows = islice(table_rows, 0, max_rows - samples)
            table_rows = chain(sample_rows, table_rows)
        else:
            if max_rows is not None and max_rows > 0:
                sample_rows = table_rows = list(islice(table_rows, max_rows))
            else:
                sample_rows = table_rows = list(table_rows)

        fields = _infer_fields(header, sample_rows, force_types, max_rows, import_fields, args, kwargs)
        # Update `header` and `import_fields` based on new `fields`
        header = list(fields.keys())
        if import_fields is None:
            import_fields = header

    else:  # using provided field types
        if isinstance(fields, Mapping):
            if not isinstance(fields, (dict, OrderedDict)):
                warning.warn(D("""\
                    Warning: unknown mapping type detected for table fields.
                    If the mapping type is unordered, results may be umpredictable
                    to supress this message use either a `dict` or an `OrderedDict`subclass
                    """))
        else:
            raise ValueError("`fields` must be an ordered Mapping")

        if skip_header:
            # If we're skipping the header probably this row is not trustworthy
            # (can be data or garbage).
            next(table_rows)

        header = make_header(list(fields.keys()))
        if import_fields is None:
            import_fields = header

        fields = OrderedDict(
            [(field_name, fields[key]) for field_name, key in zip(header, fields)]
        )

    diff = set(import_fields) - set(header)
    if diff:
        field_names = ", ".join('"{}"'.format(field) for field in diff)
        raise ValueError("Invalid field names: {}".format(field_names))
    fields = OrderedDict(
        [(field_name, fields[field_name]) for field_name in import_fields]
    )

    get_row = get_items(*map(header.index, import_fields))

    table = table_class(fields=fields, filter=query, meta=meta)
    if max_rows is not None and max_rows > 0:
        table_rows = islice(table_rows, max_rows)
    table.extend(dict(zip(import_fields, get_row(row))) for row in table_rows)

    source = table.meta.get("source", None)
    if source is not None:
        if source.should_close:
            source.fobj.close()
        if source.should_delete and Path(source.uri).exists():
            unlink(source.uri)

    return table


def prepare_to_export(table, export_fields=None, *args, **kwargs):
    # TODO: optimize for more used cases (export_fields=None)

    table_type = type(table)
    if table_type not in (FlexibleTable, Table, SQLiteTable):
        raise ValueError("Table type not recognized")

    if export_fields is None:
        # we use already slugged-fieldnames
        export_fields = table.field_names
    else:
        # we need to slug all the field names
        export_fields = make_header(export_fields)

    table_field_names = table.field_names
    diff = set(export_fields) - set(table_field_names)
    if diff:
        field_names = ", ".join('"{}"'.format(field) for field in diff)
        raise ValueError("Invalid field names: {}".format(field_names))

    yield export_fields

    field_indexes = list(map(table_field_names.index, export_fields))
    for row in table:
        yield [row[field_index] for field_index in field_indexes]


def serialize(table, *args, **kwargs):
    prepared_table = prepare_to_export(table, *args, **kwargs)

    field_names = next(prepared_table)
    yield field_names

    field_types = [table.fields[field_name] for field_name in field_names]
    for row in prepared_table:
        yield [
            field_type.serialize(value, *args, **kwargs)
            for value, field_type in zip(row, field_types)
        ]
