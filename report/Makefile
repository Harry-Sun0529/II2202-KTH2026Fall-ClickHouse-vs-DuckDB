# Build the report in the texlive container (no local TeX needed), then run the gates.
IMG := texlive/texlive:latest
ROOT := $(abspath ..)
TEX := docker run --rm -e SOURCE_DATE_EPOCH=1793750400 -e FORCE_SOURCE_DATE=1 -v $(ROOT):/work -w /work/report $(IMG)
PY := ../.venv/bin/python

.PHONY: all pdf numbers gates clean

all: numbers pdf gates

numbers:        ## numbers.tex and tables/*.tex from results/stats
	$(PY) make_numbers.py

pdf:
	$(TEX) latexmk -lualatex -interaction=nonstopmode -halt-on-error -file-line-error main.tex
	cp main.pdf II2202_Quantitative_Exercise.pdf

gates:          ## gate 4: log checks, discussion word count, number cross-check
	$(PY) check_report.py

clean:
	$(TEX) latexmk -C main.tex
