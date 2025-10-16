# Code Interpreter Test Cases

## Test 1: Simple Math Calculation
**Query:** Calculate the sum of all Maven dependency versions: 2.2.6 + 2.2.5 + 2.2.4 + 1.5.0

**Expected:** Agent uses code interpreter to calculate: 8.4.15 or 8.415

## Test 2: Data Analysis
**Query:** If we have 6 services and 15 dependencies total, what's the average dependencies per service?

**Expected:** Agent calculates 15/6 = 2.5

## Test 3: Code Generation & Execution
**Query:** Generate a Python function to validate semantic version strings and test it with "2.2.6"

**Expected:** Agent writes and executes Python code

## Test 4: JSON Parsing
**Query:** Parse this JSON and tell me the count: {"repos": ["partition", "legal", "file"], "count": null}

**Expected:** Agent executes code to parse and count: 3 repos

## Test 5: Complex Calculation
**Query:** Calculate Maven build time if each test takes 0.5 seconds and we have 250 tests across 6 services

**Expected:** Agent uses code interpreter: 250 * 0.5 = 125 seconds = 2.08 minutes
