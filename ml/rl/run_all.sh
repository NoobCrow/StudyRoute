#!/bin/sh
# Train every run used in the report: three seeds, and three reward settings (sensitivity).
# Runs are independent, so three go at a time.
cd "$(dirname "$0")"
PY=../.venv/Scripts/python.exe
$PY train_dqn.py --name dm1 --seed 1 > /dev/null 2>&1 &
$PY train_dqn.py --name dm2 --seed 2 > /dev/null 2>&1 &
$PY train_dqn.py --name dm3 --seed 3 > /dev/null 2>&1 &
wait
$PY train_dqn.py --name dm_careful --seed 1 --wrong-amount -10 > /dev/null 2>&1 &
$PY train_dqn.py --name dm_lenient --seed 1 --wrong-amount -0.5 > /dev/null 2>&1 &
$PY train_dqn.py --name dm_impatient --seed 1 --turn-cost -0.3 > /dev/null 2>&1 &
wait
