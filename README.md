# Letterbox

[![Tests](https://github.com/royadeh/letterbox-agent/actions/workflows/tests.yml/badge.svg)](https://github.com/royadeh/letterbox-agent/actions/workflows/tests.yml)

Letterbox explains dense official letters in plain language. It reads a letter
written in English and gives you:

- a plain-language explanation, in English and then in Farsi
- your options, based only on what the letter asks you to do
- a draft reply in English, with a Farsi explanation of what it says

## Who it's for

People who receive official letters in English, such as tax notices, rent
increases or benefit requests, and who would find them easier to understand in
plain English or in Farsi.

## How it stays careful

- Every fact it uses must come with the exact sentence from the letter, and
  that sentence is checked against the letter.
- It never works out a deadline, amount or date itself. If it can't confirm one,
  it says "not sure, check with the sender".
- The reply draft does not admit fault or promise payment.
- If it can't give a trustworthy answer, it says "I'm not sure, check with the
  sender", with a short reference code.

## How to run it

You need Python 3.10 or later and an Anthropic API key.

```sh
pip install .
export ANTHROPIC_API_KEY=...   # your own key, set in your shell
python -m letterbox path/to/letter.txt
```

The letter must be a plain text file. Sample letters are in `data/letters/`.
They are all made up.

## Running the tests

The tests use a fake model, so they need no API key and no network.

```sh
pip install ".[dev]"
pytest -q
```

## Disclaimer

Letterbox gives general information only. It is not legal or tax advice. Check
anything important with the sender of the letter or with a qualified adviser.
