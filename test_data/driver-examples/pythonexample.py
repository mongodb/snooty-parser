# Copyright 2017 MongoDB, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""MongoDB documentation examples in Python."""

import datetime
import sys
import threading

sys.path[0:0] = [""]

import pymongo
from pymongo.errors import ConnectionFailure, OperationFailure
from pymongo.read_concern import ReadConcern
from pymongo.read_preferences import ReadPreference
from pymongo.write_concern import WriteConcern

from test import client_context, unittest, IntegrationTest
from test.utils import rs_or_single_client


class TestSampleShellCommands(unittest.TestCase):

    @classmethod
    @client_context.require_connection
    def setUpClass(cls):
        cls.client = rs_or_single_client(w="majority")
        # Run once before any tests run.
        cls.client.pymongo_test.inventory.drop()

    @classmethod
    def tearDownClass(cls):
        client_context.client.drop_database("pymongo_test")

    def tearDown(self):
        # Run after every test.
        self.client.pymongo_test.inventory.drop()

    def test_first_three_examples(self):
        db = client_context.client.pymongo_test

        # Start Example 1
        db.inventory.insert_one(
            {"item": "canvas",
             "qty": 100,
             "tags": ["cotton"],
             "size": {"h": 28, "w": 35.5, "uom": "cm"}})
        # End Example 1

        self.assertEqual(db.inventory.count_documents({}), 1)

        # Start Example 2
        cursor = db.inventory.find({"item": "canvas"})
        # End Example 2

        self.assertEqual(cursor.count(), 1)

        # Start Example 3
        db.inventory.insert_many([
            {"item": "journal",
             "qty": 25,
             "tags": ["blank", "red"],
             "size": {"h": 14, "w": 21, "uom": "cm"}},

            {"item": "mat",
             "qty": 85,
             "tags": ["gray"],
             "size": {"h": 27.9, "w": 35.5, "uom": "cm"}},

            {"item": "mousepad",
             "qty": 25,
             "tags": ["gel", "blue"],
             "size": {"h": 19, "w": 22.85, "uom": "cm"}}])
        # End Example 3

        self.assertEqual(db.inventory.count_documents({}), 4)

    def test_query_top_level_fields(self):
        db = client_context.client.pymongo_test

        # Start Example 6
        db.inventory.insert_many([
            {"item": "journal",
             "qty": 25,
             "size": {"h": 14, "w": 21, "uom": "cm"},
             "status": "A"},
            {"item": "notebook",
             "qty": 50,
             "size": {"h": 8.5, "w": 11, "uom": "in"},
             "status": "A"},
            {"item": "paper",
             "qty": 100,
             "size": {"h": 8.5, "w": 11, "uom": "in"},
             "status": "D"},
            {"item": "planner",
             "qty": 75, "size": {"h": 22.85, "w": 30, "uom": "cm"},
             "status": "D"},
            {"item": "postcard",
             "qty": 45,
             "size": {"h": 10, "w": 15.25, "uom": "cm"},
             "status": "A"}])
        # End Example 6

        self.assertEqual(db.inventory.count_documents({}), 5)

        # Start Example 7
        cursor = db.inventory.find({})
        # End Example 7

        self.assertEqual(len(list(cursor)), 5)

        # Start Example 9
        cursor = db.inventory.find({"status": "D"})
        # End Example 9

        self.assertEqual(len(list(cursor)), 2)

        # Start Example 10
        cursor = db.inventory.find({"status": {"$in": ["A", "D"]}})
        # End Example 10

        self.assertEqual(len(list(cursor)), 5)

        # Start Example 11
        cursor = db.inventory.find({"status": "A", "qty": {"$lt": 30}})
        # End Example 11

        self.assertEqual(len(list(cursor)), 1)

        # Start Example 12
        cursor = db.inventory.find(
            {"$or": [{"status": "A"}, {"qty": {"$lt": 30}}]})
        # End Example 12

        self.assertEqual(len(list(cursor)), 3)

        # Start Example 13
        cursor = db.inventory.find({
            "status": "A",
            "$or": [{"qty": {"$lt": 30}}, {"item": {"$regex": "^p"}}]})
        # End Example 13

        self.assertEqual(len(list(cursor)), 2)
