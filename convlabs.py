#!/usr/bin/env python3

import sys, os

params = {
	"WBC": ["WBC", "White Blood Cell Count"],
	"Lymph %": ["Lymphs %", "Lymphocytes %"],
	"Mono %": ["Monos %", "Monocyte %"],
	"Gran %": ["Granulocyte %"],
	"GranIm %": ["Immature Grans %", "Immature Gran %"],
	"Neut %": ["Neutrophil %"],
	"Eos %": ["Eos %", "Eosinophil %"],
	"Bas %": ["Basophil %"],
	"Lymph #": ["Lymphs Abs", "Lymphcytes Absolute"],
	"Mono #": ["Monos Abs", "Monocyte Absolute"],
	"Gran #": ["Granulocytes Abs"],
	"GranIm #": ["Immature Grans (Abs)", "Immature Granulocytes Abs"],
	"Neut #": ["Neutrophil Absolute (ANC)", "ANC-Neutrophil Absolute"],
	"Eos #": ["Eosinophils Abs", "Eosinophil Absolute"],
	"Baso #": ["Basophil Abs"],
	"RBC": ["RBC", "Red Blood Cell Count"],
	"HGB": ["HGB", "Hemoglobin"],
	"HCT": ["HCT", "Hematocrit"],
	"MCV": ["MCV", "Mean Corpuscular Volume"],
	"MCHC": ["MCHC", "Mean Corpus HgB Conc"],
	"MCH": ["MCH", "Mean Corpus HgB"],
	"RDW": ["RDW", "RBC Distribution Width"],
	"PLT": ["PLT", "Platelets", "Platelet Count"],
	"MPV": ["MPV", "Mean Platelet Volume"],
	"Albumin": ["Albumin"],
	"ALP": ["Alkaline Phosphatase", "Alk Phos"],
	"AST": ["AST", "Aspartate Amino Trans", "Aspartate Amino Tran"],
	"ALT": ["ALT", "Alanine Amino Trans", "Alanine Amino Transf"],
	"Bilirubin": ["Bilirubin Total", "Bilirubin, Total", "Total Bilirubin.", "Bilirubin,Total"],
	"BUN": ["BUN"],
	"Calcium": ["Calcium"],
	"CO2": ["Carbon Dioxide", "CO2", "CO2."],
	"Chloride": ["Chloride"],
	"Creatinine": ["Creatinine", "Creatinine, Serum."],
	"EGFR": ["EGFR Result", "Est GFR NonAfrAm(MDRD Eqn)", "GFR Non African American"],
	"Globulin": ["Globulin"],
	"Glucose": ["Glucose", "Glucose Bld"],
	"Potassium": ["Potassium"],
	"Sodium": ["Sodium"],
	"Protein": ["Total Protein"],
	"TSH": ["TSH"],
	"PSA": ["PSA", "Prostate Spec Ag-Tosoh", "Prostate Spec Ag-TOSOH", "PSA (Hybritech)"],
}

cbc = {}

for n in range(1, len(sys.argv)):
	with open(sys.argv[n]) as f:
		labs = f.read().split('\n')
	for line in labs:
		line = line.replace('","', '"').split('"')
		line.pop(0)
		if len(line) > 0: line.pop()
		if len(line) < 4: continue
		found = False
		for column, tags in params.items():
			for t in tags:
				if t == line[2]:
					stamp = line[1]
					if stamp not in cbc:
						cbc[stamp] = {}
					try:
						x = float(line[3])
						if x > 500: x/= 1000
						x = str(x)
					except:
						x = line[3]
					cbc[stamp][column] = x
					found = True
					break
		#if not found:
		#	print(line, file=sys.stderr)

print('"When",' + '"' + '","'.join([column for column in params.keys()]) + '"')
for stamp, rec in cbc.items():
	print('"{}",'.format(stamp), end='')
	print('"' + '","'.join([rec.get(column, "") for column in params.keys()]) + '"')
