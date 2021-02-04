import io
import re
import stat
import subprocess
import tarfile
from pathlib import Path
from typing import Dict, Union, cast

import pytest

from ..diagnostics import CannotOpenFile, UnsupportedFormat
from ..types import FileId
from ..util_test import make_test

PAGE_TEXT = """
.. _mongo:

=========
``mongo``
=========

.. default-domain:: mongodb

.. contents:: On this page
   :local:
   :backlinks: none
   :depth: 1
   :class: singlecol

.. only:: html

   .. meta::
      :description: The mongo shell command man page.
      :keywords: mongo, mongodb, man page, mongo process, mongo shell

Description
-----------

.. only:: (not man)

   .. class:: hidden

      .. binary:: mongo

:binary:`~bin.mongo` is an interactive JavaScript shell interface.

.. note::

   - Thing 1

   - Thing 2

     Thing 2.5

     - Nested List

     - Still Nested

Options
-------

Core Options
~~~~~~~~~~~~

.. program:: mongo

.. option:: --shell

   Enables the shell interface. If you invoke the :program:`mongo` command
   and specify a JavaScript file as an argument, or use :option:`--eval` to
   specify JavaScript on the command line, the :option:`--shell` option
   provides the user with a shell prompt after the file finishes executing.

.. option:: --port <port>

   Specifies the port where the :binary:`~bin.mongod` or :binary:`~bin.mongos`
   instance is listening. If :option:`--port` is not specified,
   :program:`mongo` attempts to connect to port ``27017``.

.. option:: --password <password>, -p <password>

   Specifies a password with which to authenticate to a MongoDB database
   that uses authentication. Use in conjunction with the :option:`--username`
   and :option:`--authenticationDatabase` options. To force :program:`mongo` to
   prompt for a password, enter the :option:`--password` option as the
   last option and leave out the argument.

   If connecting to a `MongoDB Atlas
   <https://www.mongodb.com/cloud/atlas?tck=docs_server>`__ cluster
   using the ``MONGODB-AWS`` :option:`authentication mechanism
   <--authenticationMechanism>`, specify your AWS secret access key in
   this field, or in the :ref:`connection string
   <connection-string-auth-options>`.  Alternatively, this value may
   also be supplied as the environment variable
   ``AWS_SECRET_ACCESS_KEY``. See
   :ref:`example-connect-mongo-using-aws-iam`.

Definition List
  A definition

Another definition
  Oh there's just

  ...so many!

  .. code-block:: json

     {
        "name": "Indented Bob"
     }

.. code-block:: json

   {
      "name": "Bob"
   }

Trailing paragraph.
"""

MANPAGE_TEXT = """mongo(1)                    General Commands Manual                   mongo(1)



MONGO
DESCRIPTION
       mongo is an interactive JavaScript shell interface.

              • Thing 1

              • Thing 2

                Thing 2.5

                •   Nested List

                •   Still Nested

OPTIONS
   CORE OPTIONS
       mongo --shell

              Enables the shell interface. If you invoke the mongo command and
              specify a JavaScript file as an argument, or use --eval to spec‐
              ify  JavaScript on the command line, the --shell option provides
              the user with a shell prompt after the file finishes executing.

       mongo --port

              Specifies the port where the mongod or mongos instance  is  lis‐
              tening. If --port is not specified, mongo attempts to connect to
              port 27017.

       mongo --password, mongo -p

              Specifies a password with which to  authenticate  to  a  MongoDB
              database  that  uses authentication. Use in conjunction with the
              --username and --authenticationDatabase options. To force  mongo
              to  prompt  for  a  password, enter the --password option as the
              last option and leave out the argument.

              If connecting to a MongoDB Atlas (https://www.mongodb.com/cloud/atlas?tck=docs_server)
              cluster using  the  MONGODB-AWS
              authentication  mechanism, specify your AWS secret access key in
              this field, or in the connection  string.   Alternatively,  this
              value  may  also be supplied as the environment variable AWS_SE‐
              CRET_ACCESS_KEY. See example-connect-mongo-using-aws-iam.

       Definition List

              A definition

       Another definition

              Oh there's just

              ...so many!

                {
                   "name": "Indented Bob"
                }

         {
            "name": "Bob"
         }

       Trailing paragraph.



mongo(1)"""


def normalize(text: str) -> str:
    """Remove any non-word characters to make groff output comparable
    across platforms."""
    # Strip the strange escape characters that Groff inserts for TTYs
    text = re.sub(r".\x08", "", text)

    # Strip the header: this varies platform to platform.
    text = text.split("\n", 1)[1]

    # Remove non-word characters
    return re.sub(r"[^\w]+", "", text)


def test_manpage() -> None:
    with make_test(
        {
            Path(
                "snooty.toml"
            ): """
name = "test_manpage"

[bundle]
manpages = "manpages.tar.gz"

[manpages.mongo]
file = "index.txt"
section = 1
title = "The MongoDB Shell"

[manpages.missing]
file = "missing.txt"
section = 1
title = "This Manpage Doesn't Exist"
""",
            Path("source/index.txt"): PAGE_TEXT,
        }
    ) as result:
        # Ensure that we have an error about the missing manpage
        assert [type(diag) for diag in result.diagnostics[FileId("snooty.toml")]] == [
            CannotOpenFile
        ]

        static_files = cast(
            Dict[str, Union[str, bytes]], result.metadata["static_files"]
        )

        troff = static_files["mongo.1"]

        assert isinstance(troff, str)

        # Empty lines are discouraged in troff source
        assert "\n\n" not in troff

        try:
            # Use GNU Roff to turn our generated troff source into text we can compare.
            text = subprocess.check_output(
                ["groff", "-T", "utf8", "-t", "-man"],
                encoding="utf-8",
                input=troff,
            )
        except FileNotFoundError:
            pytest.xfail("groff is not installed")

        assert normalize(text).strip() == normalize(MANPAGE_TEXT)

        tarball_data = static_files["manpages.tar.gz"]
        assert isinstance(tarball_data, bytes)
        tarball = io.BytesIO(tarball_data)
        with tarfile.open(None, "r:*", tarball) as tf:
            names = tf.getnames()
            assert sorted(names) == sorted(["mongo.1"])
            member = tf.getmember("mongo.1")
            assert member.size == len(troff)
            assert (
                member.mode == stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH
            )


def test_bundling_error() -> None:
    with make_test(
        {
            Path(
                "snooty.toml"
            ): """
name = "test_manpage"

[bundle]
manpages = "manpages.goofy"

[manpages.mongo]
file = "index.txt"
section = 1
title = "The MongoDB Shell"
""",
            Path("source/index.txt"): PAGE_TEXT,
        }
    ) as result:
        diagnostics = result.diagnostics[FileId("snooty.toml")]
        assert UnsupportedFormat in [type(diag) for diag in diagnostics]
