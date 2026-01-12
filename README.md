[![Build & Test](https://github.com/nasa/GHRC-PyLOT/actions/workflows/build-and-test.yml/badge.svg)](https://github.com/nasa/GHRC-PyLOT/actions/workflows/build-and-test.yml)
<p align="center">
<img src="img/pylot.svg"
     alt="pylot" width=50%/>
</p>




# Overview
Python cLoud Operations Tool (PyLOT) is a python command line tool designed to help DAAC operators solve the operations edge cases that can't be solved (or which are difficult/time consuming) using [Cumulus Dashboard](https://github.com/nasa/cumulus-dashboard).
<br>
Since it is powered by Cumulus-API it will allow the operators to interact with [Cumulus stack](https://github.com/nasa/cumulus), for example to monitor the granules status, run rules, and create and update Cumulus records (collections and/or granules).
In some cases interacting with Cumulus-API via the dashboard is sufficient, but there are some edge cases that require the operator to have a tool that provides more flexibility than a Web-Based application.
<br>
PyLOT can run as a command line tool in your local machine and accept options and respond with JSON. It can also be used as a library for AWS lambda and AWS ECS tasks.
<br>
PyLOT can overcome the limitation of Cumulus-API by monitoring the status of AWS resources (Cloudwatch, SFN, S3...).
<br>
This tool will prevent reinventing the wheel, since a solution for a common problem can be easily shared among all the DAACs (sharing is caring).



```
 ____        _     ___ _____
|  _ \ _   _| |   / _ \_   _|
| |_) | | | | |  | | | || |
|  __/| |_| | |__| |_| || |
|_|    \__, |_____\___/ |_|
       |___/
```

## Prerequisites
Python 3.12+

## Installation
```jsunicoderegexp
pip install https://github.com/nasa/GHRC-PyLOT/archive/refs/tags/v3.1.0.zip
```
## Set up
```bash
Copy file
https://github.com/nasa/GHRC-PyLOT/blob/main/env.sh.example
Define environment variable and source the file
```

## 📖 Documentation
- ❓[HowTo](https://nasa.github.io/GHRC-PyLOT/howto)
- 🚀 Release note [v3.1.0](https://github.com/nasa/GHRC-PyLOT/releases/tag/v3.1.0).
